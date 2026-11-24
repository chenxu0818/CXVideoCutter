"""时间轴：刻度、关键帧标记、片段块、选区拖拽与播放头。"""

from __future__ import annotations

import bisect
from typing import List

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QScrollBar, QSizePolicy, QVBoxLayout, QWidget

from ..core.ui_scale import ui_px
from ..core.ffmpeg import format_time
from ..core.i18n import tr
from ..core.models import Segment
from ..core.theme import palette


TICK_STEPS = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600]
MIN_DRAG_SECONDS = 5.0


class _Canvas(QWidget):
    seekRequested = Signal(float)
    segmentCreated = Signal(float, float)
    positionChanged = Signal(float)   # 鼠标当前位置（用于状态栏）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = 0.0
        self.keyframes: List[float] = []
        self.segments: List[Segment] = []
        self.playhead = 0.0
        self.in_point = 0.0
        self.out_point = 0.0
        self.zoom = 1.0
        self.offset = 0.0           # 左侧对应的秒数
        self._drag_start: float | None = None
        self._drag_end = 0.0
        self.setFixedHeight(ui_px(76))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ------------------------------------------------------------------
    @property
    def visible(self) -> float:
        if self.duration <= 0:
            return 1.0
        return max(0.05, self.duration / self.zoom)

    def t_to_x(self, t: float) -> float:
        return (t - self.offset) / self.visible * self.width()

    def x_to_t(self, x: float) -> float:
        t = self.offset + x / max(1, self.width()) * self.visible
        return max(0.0, min(self.duration, t))

    def set_offset(self, seconds: float) -> None:
        self.offset = max(0.0, min(seconds, max(0.0, self.duration - self.visible)))
        self.update()

    def set_zoom(self, zoom: float, anchor_t: float | None = None) -> None:
        old_visible = self.visible
        anchor = anchor_t if anchor_t is not None else self.offset + old_visible / 2
        self.zoom = max(1.0, min(200.0, zoom))
        ratio = (anchor - self.offset) / max(old_visible, 0.001)
        self.offset = max(0.0, min(anchor - ratio * self.visible,
                                   max(0.0, self.duration - self.visible)))
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        p = palette()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(p["panel"]))
        w, h = self.width(), self.height()

        if self.duration <= 0:
            painter.setPen(QColor(p["muted"]))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("打开视频后显示时间轴"))
            return

        ruler_h = 24
        track_y = ruler_h + 6
        track_h = h - track_y - 8

        # 轨道底
        painter.fillRect(QRectF(0, track_y, w, track_h), QColor(p["panel_alt"]))

        # 刻度
        step = TICK_STEPS[-1]
        for candidate in TICK_STEPS:
            if candidate / self.visible * w >= 70:
                step = candidate
                break
        first = int(self.offset / step) * step
        t = first
        painter.setFont(QFont("Segoe UI", 8))
        while t <= self.offset + self.visible + step:
            x = self.t_to_x(t)
            if -2 <= x <= w + 2:
                painter.setPen(QPen(QColor(p["border"]), 1))
                painter.drawLine(int(x), ruler_h - 6, int(x), ruler_h)
                painter.setPen(QColor(p["muted"]))
                label = format_time(t, milliseconds=False)
                painter.drawText(int(x) + 3, 2, 90, ruler_h - 6,
                                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            t += step

        # 关键帧
        idx = bisect.bisect_left(self.keyframes, self.offset)
        painter.setPen(QPen(QColor(p["marker"]), 1))
        while idx < len(self.keyframes) and self.keyframes[idx] <= self.offset + self.visible:
            x = self.t_to_x(self.keyframes[idx])
            painter.drawLine(int(x), track_y + 2, int(x), track_y + 7)
            idx += 1

        # 片段
        colors = p["segments"]
        for i, seg in enumerate(self.segments):
            x1 = self.t_to_x(seg.start)
            x2 = self.t_to_x(seg.end)
            if x2 < 0 or x1 > w:
                continue
            color = QColor(colors[i % len(colors)])
            painter.fillRect(QRectF(x1, track_y + 10, max(2, x2 - x1), track_h - 20), color)
            painter.setPen(QColor(p["text_soft"]))
            painter.drawRect(QRectF(x1, track_y + 10, max(2, x2 - x1), track_h - 20))
            if x2 - x1 > 34:
                painter.setPen(QColor(p["text_strong"]))
                painter.drawText(QRectF(x1 + 4, track_y + 10, x2 - x1 - 8, track_h - 20),
                                 Qt.AlignmentFlag.AlignCenter, f"{tr('片段 ')}{i + 1}")

        # 入点 / 出点
        for t, color, label in ((self.in_point, p["accent"], "I"), (self.out_point, p["accent"], "O")):
            if t <= 0:
                continue
            x = self.t_to_x(t)
            painter.setPen(QPen(QColor(color), 2))
            painter.drawLine(int(x), track_y, int(x), track_y + track_h)
            painter.setPen(QColor(color))
            painter.drawText(int(x) + 2, track_y + 1, 14, 12, Qt.AlignmentFlag.AlignLeft, label)

        # 拖拽预览
        if self._drag_start is not None:
            x1, x2 = sorted((self.t_to_x(self._drag_start), self.t_to_x(self._drag_end)))
            fill = QColor(p["accent"])
            fill.setAlpha(90)
            painter.fillRect(QRectF(x1, track_y + 2, max(1, x2 - x1), track_h - 4), fill)
            painter.setPen(QPen(QColor(p["accent"]), 1))
            painter.drawRect(QRectF(x1, track_y + 2, max(1, x2 - x1), track_h - 4))

        # 播放头
        px = self.t_to_x(self.playhead)
        painter.setPen(QPen(QColor(p["playhead"]), 2))
        painter.drawLine(int(px), ruler_h - 8, int(px), track_y + track_h)

    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.duration > 0:
            t = self.x_to_t(event.position().x())
            self._drag_start = t
            self._drag_end = t
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        t = self.x_to_t(event.position().x())
        self.positionChanged.emit(t)
        if self._drag_start is not None:
            self._drag_end = t
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_start is not None:
            a, b = sorted((self._drag_start, self._drag_end))
            if b - a >= MIN_DRAG_SECONDS:
                self.segmentCreated.emit(a, b)
            else:
                self.seekRequested.emit(a)
            self._drag_start = None
            self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self.duration <= 0:
            return
        angle = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.25 if angle > 0 else 0.8
            self.set_zoom(self.zoom * factor, self.x_to_t(event.position().x()))
        else:
            self.set_offset(self.offset - angle / 120 * self.visible * 0.08)
        event.accept()


class Timeline(QWidget):
    """带水平滚动条的时间轴组件。"""

    seekRequested = Signal(float)
    segmentCreated = Signal(float, float)
    positionChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.canvas = _Canvas(self)
        self.scroll = QScrollBar(Qt.Orientation.Horizontal, self)
        layout.addWidget(self.canvas)
        layout.addWidget(self.scroll)

        self.canvas.seekRequested.connect(self.seekRequested.emit)
        self.canvas.segmentCreated.connect(self.segmentCreated.emit)
        self.canvas.positionChanged.connect(self.positionChanged.emit)
        self.scroll.valueChanged.connect(self._on_scroll)

        self._updating = False

    def _on_scroll(self, value: int) -> None:
        if self._updating:
            return
        self.canvas.set_offset(value / 1000.0)

    def _sync_scroll(self) -> None:
        self._updating = True
        max_ms = max(0, int((self.canvas.duration - self.canvas.visible) * 1000))
        self.scroll.setRange(0, max_ms)
        self.scroll.setValue(int(self.canvas.offset * 1000))
        self.scroll.setEnabled(max_ms > 0)
        self._updating = False

    # ------------------------------------------------------------------
    def setMedia(self, duration: float, keyframes: List[float]) -> None:  # noqa: N802
        self.canvas.duration = duration
        self.canvas.keyframes = keyframes
        self.canvas.zoom = 1.0
        self.canvas.offset = 0.0
        self.canvas.playhead = 0.0
        self._sync_scroll()
        self.canvas.update()

    def setSegments(self, segments: List[Segment]) -> None:  # noqa: N802
        self.canvas.segments = segments
        self.canvas.update()

    def setInOut(self, in_point: float, out_point: float) -> None:  # noqa: N802
        self.canvas.in_point = in_point
        self.canvas.out_point = out_point
        self.canvas.update()

    def setPlayhead(self, t: float) -> None:  # noqa: N802
        self.canvas.playhead = t
        self.canvas.update()

    def zoomIn(self) -> None:  # noqa: N802
        self.canvas.set_zoom(self.canvas.zoom * 1.5)
        self._sync_scroll()

    def zoomOut(self) -> None:  # noqa: N802
        self.canvas.set_zoom(self.canvas.zoom / 1.5)
        self._sync_scroll()
