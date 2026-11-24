"""界面辅助工具：后台缩略图加载、时间输入控件。"""

from __future__ import annotations

import os
import tempfile
from collections import deque
from typing import Tuple

from PySide6.QtCore import QMutex, QMutexLocker, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QLineEdit, QSizePolicy, QWidget

from ..core.ui_scale import ui_px
from ..core.ffmpeg import extract_frame, format_time, get_keyframes, parse_time


class FrameView(QWidget):
    """用 ffmpeg 抽取的静帧显示预览：保持宽高比居中显示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()

    def setPixmapPath(self, path: str) -> bool:  # noqa: N802
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return False
        self.setPixmap(pixmap)
        return True

    def setPixmap(self, pixmap: QPixmap) -> None:  # noqa: N802
        if pixmap.isNull():
            return
        self._pixmap = pixmap
        self.update()

    def clear(self) -> None:
        self._pixmap = QPixmap()
        self.update()

    def has_pixmap(self) -> bool:
        return not self._pixmap.isNull()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        if self._pixmap.isNull():
            return
        scaled = self._pixmap.scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


class PreviewFrameLoader(QThread):
    """后台按指定时间点抽取预览帧；多次请求只保留最后一次，避免逐帧时堆积。

    每次请求使用独立输出文件和递增序号，避免旧请求覆盖新文件、或过期结果
    把主画面刷回旧帧。
    """

    frame_ready = Signal(int, str)  # 请求序号, 生成的图片路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending = None
        self._mutex = QMutex()
        self._stop = False
        self._req_id = 0

    def request(self, video_path: str, time: float, out_path: str) -> None:
        with QMutexLocker(self._mutex):
            self._req_id += 1
            base, ext = os.path.splitext(out_path)
            unique = f"{base}_{self._req_id}{ext}"
            self._pending = (self._req_id, video_path, max(0.0, float(time)), unique)
        if not self.isRunning():
            self.start()

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        while not self._stop:
            with QMutexLocker(self._mutex):
                item = self._pending
                self._pending = None
            if not item:
                self.msleep(15)
                continue
            rid, video_path, t, out = item
            extract_frame(video_path, t, out, 0)
            if os.path.isfile(out):
                self.frame_ready.emit(rid, out)
            # 只保留最近几张，避免临时文件无限累积
            try:
                directory = os.path.dirname(out) or "."
                prefix = os.path.basename(out).split("_")[0] + "_"
                for name in os.listdir(directory):
                    if not name.startswith(prefix):
                        continue
                    try:
                        other_id = int(os.path.splitext(name[len(prefix):])[0])
                    except ValueError:
                        continue
                    if other_id < rid - 2:
                        os.remove(os.path.join(directory, name))
            except OSError:
                pass


class KeyframeLoader(QThread):
    """后台扫描关键帧。"""

    finished_load = Signal(list)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self) -> None:
        self.finished_load.emit(get_keyframes(self.path))


class ThumbnailLoader(QThread):
    """后台抽取片段首帧，避免阻塞界面。"""

    thumb_ready = Signal(int, str)  # segment id, thumbnail path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = deque()
        self._mutex = QMutex()
        self._stop = False

    def add(self, seg_id: int, video_path: str, time: float, width: int = 320) -> str:
        cache_dir = os.path.join(tempfile.gettempdir(), "cx-video-cutter-thumbs")
        os.makedirs(cache_dir, exist_ok=True)
        out_path = os.path.join(cache_dir, f"seg_{seg_id}_{int(time * 1000)}.jpg")
        with QMutexLocker(self._mutex):
            self._queue.append((seg_id, video_path, time, width, out_path))
        if not self.isRunning():
            self.start()
        return out_path

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        # 保持线程存活而不是队列空就退出：否则 add() 在线程即将退出时入队，
        # isRunning() 仍为 True 导致不再 start()，该缩略图就永远不会生成。
        while not self._stop:
            with QMutexLocker(self._mutex):
                item: Tuple[int, str, float, int, str] | None = (
                    self._queue.popleft() if self._queue else None
                )
            if item is None:
                self.msleep(20)
                continue
            seg_id, path, time, width, out = item
            if extract_frame(path, time, out, width):
                self.thumb_ready.emit(seg_id, out)


class TimeEdit(QLineEdit):
    """接受 HH:MM:SS.mmm 格式的时间输入框。"""

    timeChanged = Signal(float)

    def __init__(self, seconds: float = 0.0, parent=None):
        super().__init__(parent)
        self.setSeconds(seconds)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(ui_px(110))
        self.editingFinished.connect(self._on_editing_finished)
        self._value = seconds

    def _on_editing_finished(self) -> None:
        value = parse_time(self.text())
        self.setSeconds(value)
        self.timeChanged.emit(value)

    def setSeconds(self, seconds: float) -> None:
        self._value = max(0.0, float(seconds))
        self.setText(format_time(self._value))

    def seconds(self) -> float:
        return self._value
