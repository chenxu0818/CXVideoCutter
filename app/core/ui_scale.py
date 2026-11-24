"""界面缩放：Qt 已按系统显示缩放（devicePixelRatio）处理 DPI，
本模块只做两件事：

1. 在“屏幕逻辑分辨率很高、但系统缩放仍为 100%”时做适度补偿；
2. 提供用户可覆盖的缩放比例，供不同观感偏好手动微调。

系统缩放已生效时自动模式返回 1.0，避免与 Qt 原生缩放叠加导致界面过大。
音量条等明确不参与缩放的控件不使用 ui_px()，并在样式表里单独固定尺寸。
"""
from __future__ import annotations

import re

from PySide6.QtGui import QGuiApplication

AUTO = "auto"
SCALE_CHOICES = [
    (AUTO, "自动"),
    ("0.9", "90%"),
    ("1.0", "100%"),
    ("1.1", "110%"),
    ("1.25", "125%"),
    ("1.5", "150%"),
]

_current = 1.0
_choice = AUTO


def apply(choice: str | None) -> float:
    """应用缩放选择，返回实际生效的缩放系数。"""
    global _current, _choice
    _choice = choice or AUTO
    if _choice == AUTO:
        _current = _detect_auto()
    else:
        try:
            _current = min(max(float(_choice), 0.7), 2.0)
        except (TypeError, ValueError):
            _current = 1.0
    return _current


def _detect_auto() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app else None
    if screen is None:
        return 1.0
    # 系统缩放已经生效：Qt 自己会按 dpr 放大，不再叠加。
    if screen.devicePixelRatio() > 1.05:
        return 1.0
    # 高分辨率但系统仍 100%：按逻辑宽度做阶梯补偿。
    width = screen.size().width()
    if width >= 3000:
        return 1.5
    if width >= 2200:
        return 1.25
    return 1.0


def factor() -> float:
    return _current


def ui_px(value: float) -> int:
    """把设计时的逻辑像素换算为当前缩放下的像素值。"""
    return max(1, round(float(value) * _current))


def scale_stylesheet(qss: str, fixed_css: str = "") -> str:
    """按比例缩放样式表里的所有 px 尺寸，并追加不缩放的固定规则。"""
    def _repl(match: re.Match[str]) -> str:
        value = float(match.group(1)) * _current
        if value < 0:
            return f"-{max(1, round(-value))}px"
        return f"{max(1, round(value))}px"

    scaled = re.sub(r"(-?\d+(?:\.\d+)?)px", _repl, qss)
    if fixed_css:
        scaled += "\n/* 固定尺寸控件：不随界面缩放 */\n" + fixed_css
    return scaled
