"""视频预览下方的帧预览条：当前帧居中，左侧为前面的帧，右侧为后面的帧。

帧位数量根据控件当前宽度实时计算，窗口最大化时自动显示更多帧。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections import OrderedDict
from typing import List, Tuple

from PySide6.QtCore import QMutex, QMutexLocker, Qt, QThread, Signal
from PySide6.QtGui import QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from ..core.ui_scale import ui_px
from ..core.ffmpeg import extract_frame_window, format_time


CACHE_DIR = os.path.join(tempfile.gettempdir(), "cxvc-filmstrip")
CACHE_IMAGES = os.path.join(CACHE_DIR, "images")
MIN_CELL_WIDTH = 108   # 单个帧位的最小宽度
MAX_CELLS = 21         # 上限，避免一次抽取过多帧拖慢界面
MAX_CACHE = 320        # 缓存帧数，逐帧来回移动时几乎不用重新解码
PREFETCH = 8           # 每次抽取时向前/向后多取几帧，连续逐帧时直接命中缓存


class FilmstripLoader(QThread):
    """后台抽取当前帧前后的画面。

    优化点：
    1. 连续缺失的帧用一次 ffmpeg 进程批量抽取，避免 N 次进程启动。
    2. 已抽过的帧按 (文件, 时间点) 缓存；逐帧移动时绝大多数帧直接命中缓存。
    3. 新请求覆盖未完成的旧请求。
    """

    frames_ready = Signal(int, list)  # request id, [(time, path), ...]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._pending = None
        self._req_id = 0
        self._stop = False
        self._cache: "OrderedDict[str, str]" = OrderedDict()

    def request(
        self, video_path: str, center: float, step: float,
        duration: float = 0.0, count: int = 7,
    ) -> None:
        with QMutexLocker(self._mutex):
            self._req_id += 1
            self._pending = (
                self._req_id,
                video_path,
                max(0.0, float(center)),
                max(0.0001, float(step)),
                max(0.0, float(duration)),
                max(1, int(count)),
            )
        if not self.isRunning():
            self.start()

    def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------------
    # 帧缓存
    # ------------------------------------------------------------------
    @staticmethod
    def _key(video: str, t: float, step: float) -> str:
        # 以帧序号为键，避免浮点误差让同一帧生成不同缓存项
        return f"{video}|{int(round(t / step))}"

    @classmethod
    def _image_path(cls, video: str, t: float, step: float) -> str:
        digest = hashlib.md5(cls._key(video, t, step).encode("utf-8")).hexdigest()[:16]
        return os.path.join(CACHE_IMAGES, f"{digest}.jpg")

    def _cached(self, video: str, t: float, step: float) -> str:
        key = self._key(video, t, step)
        path = self._cache.get(key)
        if path and os.path.isfile(path):
            self._cache.move_to_end(key)
            return path
        if path:
            self._cache.pop(key, None)
        return ""

    def _store(self, video: str, t: float, step: float, src: str) -> str:
        if not src or not os.path.isfile(src):
            return ""
        dst = self._image_path(video, t, step)
        try:
            if os.path.abspath(src) != os.path.abspath(dst):
                os.replace(src, dst)
        except OSError:
            try:
                with open(src, "rb") as f_in, open(dst, "wb") as f_out:
                    f_out.write(f_in.read())
            except OSError:
                return ""
        key = self._key(video, t, step)
        self._cache[key] = dst
        self._cache.move_to_end(key)
        while len(self._cache) > MAX_CACHE:
            _, old = self._cache.popitem(last=False)
            try:
                os.remove(old)
            except OSError:
                pass
        return dst

    # ------------------------------------------------------------------
    def run(self) -> None:
        try:
            os.makedirs(CACHE_IMAGES, exist_ok=True)
        except OSError:
            pass
        while not self._stop:
            with QMutexLocker(self._mutex):
                item = self._pending
                self._pending = None
            if item is None:
                self.msleep(15)
                continue

            rid, video, center, step, duration, count = item
            half = count // 2
            times = [center + (i - half) * step for i in range(count)]
            results: List[Tuple[float, str]] = [(t, "") for t in times]

            # 先命中缓存，再把连续缺失的格子合并成区间批量抽取
            missing: List[int] = []
            runs: List[List[int]] = []
            for i, t in enumerate(times):
                if t < 0 or (duration > 0 and t >= duration - 0.0001):
                    continue
                cached = self._cached(video, t, step)
                if cached:
                    results[i] = (t, cached)
                    if missing:
                        runs.append(missing)
                        missing = []
                else:
                    missing.append(i)
            if missing:
                runs.append(missing)

            aborted = False
            for run in runs:
                with QMutexLocker(self._mutex):
                    if self._pending is not None:
                        aborted = True
                        break

                start_t = times[run[0]]
                extract_count = len(run)
                # 窗口边缘额外预取，连续逐帧/小幅移动时后续请求直接命中缓存
                if run[-1] >= count - 1 and duration > 0:
                    extra = min(PREFETCH, max(0, int((duration - times[-1]) / step) - 1))
                    extract_count += extra
                if run[0] <= 0:
                    back = min(PREFETCH, int(start_t / step))
                    if back > 0:
                        start_t -= back * step
                        extract_count += back

                prefix = f"win_{rid}_{run[0]}"
                files = extract_frame_window(
                    video, start_t, extract_count, CACHE_DIR, prefix, 240
                )
                if len(files) < len(run):
                    aborted = True
                    break
                for j, src in enumerate(files):
                    self._store(video, start_t + j * step, step, src)
                for idx in run:
                    path = self._cached(video, times[idx], step)
                    results[idx] = (times[idx], path)

            if not aborted:
                self.frames_ready.emit(rid, results)


class _FilmCell(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("filmCell")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.time = -1.0
        self._pixmap = QPixmap()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)

        self.thumb = QLabel()
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFixedHeight(ui_px(60))
        layout.addWidget(self.thumb)

        self.label = QLabel("-")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.setHighlight(False)

    def setPixmap(self, path: str) -> None:  # noqa: N802
        pix = QPixmap(path)
        self._pixmap = pix if not pix.isNull() else QPixmap()
        if self._pixmap.isNull():
            self.thumb.clear()
        else:
            self.thumb.setPixmap(self._pixmap.scaled(
                self.thumb.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def clearPixmap(self) -> None:  # noqa: N802
        self._pixmap = QPixmap()
        self.thumb.clear()

    def setHighlight(self, on: bool) -> None:  # noqa: N802
        if on:
            color = QApplication.palette().color(QPalette.ColorRole.Highlight).name()
            self.setStyleSheet(
                f"QFrame#filmCell {{ border: 2px solid {color}; border-radius: 4px; }}"
            )
        else:
            self.setStyleSheet(
                "QFrame#filmCell { border: 1px solid transparent; border-radius: 4px; }"
            )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            self.thumb.setPixmap(self._pixmap.scaled(
                self.thumb.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.time >= 0:
            self.clicked.emit()
        super().mousePressEvent(event)


class FilmstripWidget(QWidget):
    """一排帧缩略图；数量随宽度变化，点击任意帧可定位到该时间点。"""

    frameClicked = Signal(float)
    countChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.count = 0
        self._cells: List[_FilmCell] = []
        self._root = QHBoxLayout(self)
        self._root.setContentsMargins(4, 2, 4, 2)
        self._root.setSpacing(4)
        self.setFixedHeight(ui_px(98))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------------
    # 自适应数量
    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._ensure_count()

    def _ensure_count(self) -> None:
        width = max(0, self.contentsRect().width())
        count = width // MIN_CELL_WIDTH
        count = max(3, min(MAX_CELLS, int(count)))
        if count % 2 == 0:       # 必须保留唯一的正中间帧
            count -= 1
        if count != self.count:
            self._build_cells(count)
            self.countChanged.emit(count)

    def _build_cells(self, count: int) -> None:
        while self._root.count():
            item = self._root.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cells.clear()
        for i in range(count):
            cell = _FilmCell(self)
            cell.clicked.connect(lambda _checked=False, idx=i: self._on_cell_clicked(idx))
            self._root.addWidget(cell, 1)
            self._cells.append(cell)
        self.count = count

    def _on_cell_clicked(self, index: int) -> None:
        if 0 <= index < len(self._cells) and self._cells[index].time >= 0:
            self.frameClicked.emit(self._cells[index].time)

    def pixmap_for_time(self, t: float) -> QPixmap:
        """返回指定时间帧的已缓存图片（用于点击后立即刷新主画面）。"""
        for cell in self._cells:
            if abs(cell.time - t) < 0.0001:
                return QPixmap(cell._pixmap)
        return QPixmap()

    # ------------------------------------------------------------------
    def set_frames(self, frames: List[Tuple[float, str]]) -> None:  # noqa: N802
        half = self.count // 2
        for idx, (t, path) in enumerate(frames[:self.count]):
            cell = self._cells[idx]
            cell.time = t
            if path and os.path.isfile(path):
                cell.setPixmap(path)
            else:
                cell.clearPixmap()
            cell.label.setText(format_time(t, milliseconds=False) if t >= 0 else "-")
            cell.setHighlight(idx == half)
        for cell in self._cells[len(frames):]:
            cell.time = -1.0
            cell.clearPixmap()
            cell.label.setText("-")
            cell.setHighlight(False)

    def clear(self) -> None:
        for cell in self._cells:
            cell.time = -1.0
            cell.clearPixmap()
            cell.label.setText("-")
            cell.setHighlight(False)
