"""分辨率自适应：系统 DPI + 按逻辑分辨率的自动档 + 手动比例。

设计参考 CXPurePlayer：Qt 负责系统级 DPI（devicePixelRatio），本模块只负责
应用层的统一尺寸源 Metrics。所有界面固定尺寸都通过 Metrics.s() / ui_px()
派生；字体通过 Metrics.apply_font() 统一设置；缩放变化时重新生成样式表、
字体，并按比例调整已有控件的几何尺寸与窗口大小。

音量条明确不参与缩放：其 objectName 为 volumeSlider，几何与 QSS 均单独固定。
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QHeaderView, QLayout, QSplitter, QWidget

# 界面自适应范围：最低 720p，最高 6K（按逻辑分辨率较短边计算）。
MIN_SUPPORTED_SHORT_SIDE = 720
MAX_SUPPORTED_SHORT_SIDE = 3456

# 自动档参考表：(逻辑分辨率较短边上限, scale)
_AUTO_TIERS = [
    (MIN_SUPPORTED_SHORT_SIDE, 1.0),
    (1080, 1.0),
    (1440, 1.25),
    (2160, 1.6),
    (2880, 1.8),
    (MAX_SUPPORTED_SHORT_SIDE, 2.0),
]

AUTO = "auto"
MANUAL = "manual"

_metrics: Metrics | None = None


def configure_high_dpi() -> None:
    """必须在创建 QApplication 之前调用。"""
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
    if hasattr(QGuiApplication, "setHighDpiScaleFactorRoundingPolicy"):
        try:
            from PySide6.QtCore import Qt
            QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except Exception:
            pass


def detect_auto_scale() -> float:
    """按主屏“系统缩放后的逻辑分辨率”较短边取自动档，避免与 Qt DPI 叠加。"""
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return 1.0
    size = screen.size()
    short_side = max(MIN_SUPPORTED_SHORT_SIDE,
                     min(MAX_SUPPORTED_SHORT_SIDE, min(size.width(), size.height())))
    for limit, scale in _AUTO_TIERS:
        if short_side <= limit:
            return scale
    return 2.0


class Metrics(QObject):
    """全局尺寸源：界面固定尺寸、字体、样式表都从这里派生。"""

    scaleChanged = Signal(float)

    def __init__(self, settings) -> None:
        super().__init__()
        self._settings = settings
        self._scale = 1.0
        self.recompute()

    # --- 缩放计算 ---
    def recompute(self) -> float:
        if self._settings.ui_scale_mode() == MANUAL:
            scale = self._settings.ui_scale_percent() / 100.0
        else:
            scale = detect_auto_scale()
        scale = max(0.8, min(2.0, float(scale)))
        if abs(scale - self._scale) > 1e-6:
            self._scale = scale
            self.scaleChanged.emit(scale)
        return self._scale

    @property
    def scale(self) -> float:
        return self._scale

    def mode_text(self) -> str:
        mode = "手动" if self._settings.ui_scale_mode() == MANUAL else "自动"
        return f"{mode} / {int(round(self._scale * 100))}%"

    # --- 尺寸派生 ---
    def s(self, px: float) -> int:
        return max(1, int(round(px * self._scale)))

    def font(self, pt: float) -> float:
        return max(8.0, round(pt * self._scale, 1))

    def icon(self, size: int) -> int:
        return self.s(size)

    def apply_font(self, app: QApplication | None = None) -> None:
        app = app or QApplication.instance()
        if app is None:
            return
        if sys.platform == "win32":
            family = "Microsoft YaHei"
        elif sys.platform == "darwin":
            family = "PingFang SC"
        else:
            family = "Noto Sans CJK SC"
        font = QFont(family)
        font.setPointSizeF(self.font(9))
        app.setFont(font)


def init_metrics(settings) -> Metrics:
    """在 QApplication 创建后调用，建立全局 Metrics。"""
    global _metrics
    _metrics = Metrics(settings)
    return _metrics


def metrics() -> Metrics | None:
    return _metrics


def apply(choice: str | None) -> float:
    """兼容旧接口：按字符串比例直接设置缩放。"""
    global _metrics
    if _metrics is None:
        class _FallbackSettings:
            def ui_scale_mode(self) -> str:
                return AUTO if choice in (None, AUTO) else MANUAL
            def ui_scale_percent(self) -> int:
                try:
                    return int(round(float(choice) * 100))
                except (TypeError, ValueError):
                    return 100
        _metrics = Metrics(_FallbackSettings())
    return _metrics.scale


def factor() -> float:
    return _metrics.scale if _metrics is not None else 1.0


def ui_px(value: float) -> int:
    """把设计时的逻辑像素换算为当前缩放下的像素值。"""
    return _metrics.s(value) if _metrics is not None else max(1, round(float(value)))


def scale_stylesheet(qss: str, fixed_css: str = "") -> str:
    """按比例缩放样式表里的所有 px 尺寸，并追加不缩放的固定规则。"""
    scale = factor()

    def _repl(match: re.Match[str]) -> str:
        value = float(match.group(1)) * scale
        if value < 0:
            return f"-{max(1, round(-value))}px"
        return f"{max(1, round(value))}px"

    scaled = re.sub(r"(-?\d+(?:\.\d+)?)px", _repl, qss)
    if fixed_css:
        scaled += "\n/* 固定尺寸控件：不随界面缩放 */\n" + fixed_css
    return scaled


# ---------------------------------------------------------------------------
# 缩放变化时对已有控件做等比调整（替代逐个控件手写 apply_scale）
# ---------------------------------------------------------------------------
QWIDGETSIZE_MAX = 16777215


def _scaled(value: int, ratio: float) -> int:
    return max(1, int(round(value * ratio))) if value > 0 else value


def rescale_layout(layout: QLayout, ratio: float) -> None:
    left, top, right, bottom = layout.getContentsMargins()
    layout.setContentsMargins(_scaled(left, ratio), _scaled(top, ratio),
                              _scaled(right, ratio), _scaled(bottom, ratio))
    spacing = layout.spacing()
    if spacing > 0:
        layout.setSpacing(_scaled(spacing, ratio))


def rescale_widget_tree(root: QWidget | None, ratio: float) -> None:
    """对已构建的控件树按 ratio 等比调整固定尺寸、边距、列宽和分隔条。"""
    if abs(ratio - 1.0) < 1e-6 or root is None:
        return

    widgets: list[QWidget] = [root]
    widgets.extend(root.findChildren(QWidget))

    for widget in widgets:
        if widget.objectName() == "volumeSlider":
            continue  # 音量条保持原始大小

        if isinstance(widget, QSplitter):
            widget.setSizes([_scaled(s, ratio) for s in widget.sizes()])

        min_w, max_w = widget.minimumWidth(), widget.maximumWidth()
        min_h, max_h = widget.minimumHeight(), widget.maximumHeight()
        if min_w == max_w and min_w > 0:
            widget.setFixedWidth(_scaled(min_w, ratio))
        else:
            if min_w > 0:
                widget.setMinimumWidth(_scaled(min_w, ratio))
            if 0 < max_w < QWIDGETSIZE_MAX:
                widget.setMaximumWidth(max(_scaled(min_w, ratio), _scaled(max_w, ratio)))
        if min_h == max_h and min_h > 0:
            widget.setFixedHeight(_scaled(min_h, ratio))
        else:
            if min_h > 0:
                widget.setMinimumHeight(_scaled(min_h, ratio))
            if 0 < max_h < QWIDGETSIZE_MAX:
                widget.setMaximumHeight(max(_scaled(min_h, ratio), _scaled(max_h, ratio)))

        if hasattr(widget, "columnCount") and hasattr(widget, "setColumnWidth"):
            try:
                for column in range(widget.columnCount()):
                    widget.setColumnWidth(column, _scaled(widget.columnWidth(column), ratio))
            except Exception:
                pass

    for widget in widgets:
        if isinstance(widget, QHeaderView):
            try:
                widget.setDefaultSectionSize(_scaled(widget.defaultSectionSize(), ratio))
            except Exception:
                pass

    layouts: list[QLayout] = []
    for widget in widgets:
        layout = widget.layout()
        if layout is not None and layout not in layouts:
            layouts.append(layout)
        for child in widget.findChildren(QLayout):
            if child not in layouts:
                layouts.append(child)
    for layout in layouts:
        rescale_layout(layout, ratio)
