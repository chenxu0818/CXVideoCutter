"""支持触控板手势的滑块：双指平移/轻扫可调节进度条与音量条。

Windows 上普通鼠标滚轮仍按 Qt 默认行为工作；macOS 触控板的双指滑动会以
QNativeGestureEvent(PanNativeGesture / SwipeNativeGesture) 送达，这里把它
换算为滑块数值变化，并通过 userValueChanged 信号通知业务层。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QSlider


class GestureSlider(QSlider):
    """可用触控板手势调节的 QSlider。"""

    userValueChanged = Signal(int)

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        # 每像素手势位移对应的最小数值变化；业务层可按范围重写
        self.gesture_unit = 1.0

    # ------------------------------------------------------------------
    def event(self, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.NativeGesture:
            kind = event.gestureType()
            if kind in (
                Qt.NativeGestureType.PanNativeGesture,
                Qt.NativeGestureType.SwipeNativeGesture,
            ):
                delta = event.delta()
                dx = delta.x() if hasattr(delta, "x") else 0.0
                if abs(dx) < 0.01:
                    dx = float(event.value()) * 20.0
                self._apply_gesture(dx)
                event.accept()
                return True
            if kind == Qt.NativeGestureType.SmartZoomNativeGesture:
                self._apply_gesture(float(event.value()) * 10.0)
                event.accept()
                return True
        return super().event(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        # 触控板横向滑动在部分平台表现为水平滚轮；用它来调节滑块。
        angle = event.angleDelta()
        if angle.x() and not angle.y():
            self._apply_gesture(angle.x() / 120.0 * 12.0)
            event.accept()
            return
        super().wheelEvent(event)

    # ------------------------------------------------------------------
    def _apply_gesture(self, delta: float) -> None:
        change = int(round(delta * self.gesture_unit))
        if change == 0:
            # 保证小幅滑动也有响应
            change = 1 if delta > 0 else -1
        new_value = max(self.minimum(), min(self.maximum(), self.value() + change))
        if new_value == self.value():
            return
        self.setValue(new_value)
        self.userValueChanged.emit(new_value)
