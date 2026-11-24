"""界面主题：多套科技现代风格配色，统一生成全局样式表。"""

from __future__ import annotations

import os
import tempfile

from .ui_scale import scale_stylesheet

THEMES = {
    "default": {
        "name": "默认深色",
        "palette": {
            "bg": "#16191e", "panel": "#1d2127", "panel_alt": "#23272e",
            "border": "#333a44", "text": "#d8dee7", "text_strong": "#e8edf4",
            "text_soft": "#b9c2ce", "muted": "#8d97a5",
            "accent": "#2f6fb0", "accent_hover": "#397ec2", "accent_text": "#ffffff",
            "toolbar": "#20242b", "menu": "#242a32", "input": "#22272e",
            "progress": "#3d8bd6", "playhead": "#ff5a5f", "marker": "#5c6b7d",
            "segments": ["#2f6fb0", "#2b8a6a", "#9a6b2f", "#7b4fa8", "#a5475c"],
        },
    },
    "ocean": {
        "name": "深空蓝",
        "palette": {
            "bg": "#0b1424", "panel": "#0f1d33", "panel_alt": "#132744",
            "border": "#1f3b63", "text": "#d6e9ff", "text_strong": "#f0f7ff",
            "text_soft": "#a9c9ee", "muted": "#6f93bf",
            "accent": "#00b4d8", "accent_hover": "#21c8e8", "accent_text": "#04121f",
            "toolbar": "#0d1a2d", "menu": "#10203a", "input": "#0c1a2e",
            "progress": "#00b4d8", "playhead": "#ff4d6d", "marker": "#2c5b8c",
            "segments": ["#00b4d8", "#4361ee", "#7b61ff", "#00c2a8", "#f72585"],
        },
    },
    "nebula": {
        "name": "霓虹紫",
        "palette": {
            "bg": "#120d1f", "panel": "#1a1230", "panel_alt": "#24183f",
            "border": "#38275e", "text": "#e7ddff", "text_strong": "#f7f0ff",
            "text_soft": "#c3aee9", "muted": "#8e78ba",
            "accent": "#b63ff5", "accent_hover": "#cc63fb", "accent_text": "#ffffff",
            "toolbar": "#160f27", "menu": "#1d1434", "input": "#160f27",
            "progress": "#b63ff5", "playhead": "#ff4d9d", "marker": "#57437f",
            "segments": ["#b63ff5", "#7b61ff", "#ff4d9d", "#00c2ff", "#a3ff12"],
        },
    },
    "aurora": {
        "name": "极光绿",
        "palette": {
            "bg": "#0a1714", "panel": "#10221d", "panel_alt": "#16302a",
            "border": "#245345", "text": "#d8f5e9", "text_strong": "#effff8",
            "text_soft": "#a6d8c4", "muted": "#6fa38f",
            "accent": "#00d68f", "accent_hover": "#21e6a2", "accent_text": "#04251a",
            "toolbar": "#0c1c18", "menu": "#112620", "input": "#0c1c18",
            "progress": "#00d68f", "playhead": "#ff6b6b", "marker": "#2e6f5c",
            "segments": ["#00d68f", "#00b4d8", "#a3ff12", "#7b61ff", "#ffb703"],
        },
    },
    "ember": {
        "name": "赛博橙",
        "palette": {
            "bg": "#1a120d", "panel": "#241811", "panel_alt": "#302015",
            "border": "#573823", "text": "#f6e6d8", "text_strong": "#fff5ec",
            "text_soft": "#d9bba3", "muted": "#a37c60",
            "accent": "#ff8c2b", "accent_hover": "#ffa04d", "accent_text": "#1a0e05",
            "toolbar": "#1f150f", "menu": "#261a12", "input": "#1f150f",
            "progress": "#ff8c2b", "playhead": "#ff3b6b", "marker": "#7a5234",
            "segments": ["#ff8c2b", "#ff4d6d", "#ffd166", "#9b5de5", "#00c2a8"],
        },
    },
    "techblue": {
        "name": "科技蓝",
        # 参考 Element Plus 官方色板：primary #409eff，light-3 #79bbff，
        # light-7 #c6e2ff，light-9 #ecf5ff，dark-2 #337ecc；
        # 文字 #303133 / #606266 / #909399，边框 #dcdfe6。
        "palette": {
            "bg": "#f0f5ff", "panel": "#ffffff", "panel_alt": "#f5f8ff",
            "border": "#dcdfe6", "text": "#303133", "text_strong": "#1f2d3d",
            "text_soft": "#606266", "muted": "#909399",
            "accent": "#409eff", "accent_hover": "#337ecc", "accent_text": "#ffffff",
            "toolbar": "#ffffff", "menu": "#ffffff", "input": "#ffffff",
            "progress": "#409eff", "playhead": "#f56c6c", "marker": "#c0c4cc",
            "segments": ["#409eff", "#67c23a", "#e6a23c", "#f56c6c", "#909399"],
        },
        "extra_css": """
    /* Element Plus 风格的浅色企业蓝：交互态使用 primary 的浅色阶 */
    QToolBar { border-bottom: 2px solid #409eff; }
    QPushButton { background: #ffffff; }
    QPushButton:hover { background: #ecf5ff; border-color: #409eff; color: #409eff; }
    QPushButton:pressed { background: #d9ecff; }
    QPushButton#primaryButton {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #409eff, stop:1 #337ecc);
        border: 1px solid #337ecc; border-radius: 6px; padding: 6px 14px;
    }
    QPushButton#primaryButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #337ecc, stop:1 #2b5f95);
    }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #409eff; }
    QTreeWidget::item:selected, QListWidget::item:selected {
        background: #ecf5ff; color: #409eff;
    }
    QHeaderView::section { border-bottom: 1px solid #dcdfe6; }
    QStatusBar { border-top: 1px solid #dcdfe6; }
    QWidget#vsep { background: #c0c4cc; }
    QFrame#segmentItem { background: #ffffff; }
    QFrame#segmentItem:hover { background: #ecf5ff; }
    QLabel#thumb { background: #f5f8ff; }
        """,
    },
    "stellar": {
        "name": "星空科技",
        "starfield": True,
        "palette": {
            "bg": "#070b1a", "panel": "#0d1329", "panel_alt": "#141c39",
            "border": "#263260", "text": "#dfe7ff", "text_strong": "#f6f9ff",
            "text_soft": "#b0c0f0", "muted": "#7b8bc4",
            "accent": "#5b8cff", "accent_hover": "#7aa5ff", "accent_text": "#ffffff",
            "toolbar": "#0a1024", "menu": "#101838", "input": "#0b122a",
            "progress": "#5b8cff", "playhead": "#ff5d8f", "marker": "#39477c",
            "segments": ["#5b8cff", "#9b6bff", "#00d2d3", "#ff6b9d", "#ffd166"],
        },
    },
}

THEME_CHOICES = [(code, data["name"]) for code, data in THEMES.items()]
DEFAULT_THEME = "default"
_current = DEFAULT_THEME


def current_theme() -> str:
    return _current


def set_theme(code: str) -> None:
    global _current
    _current = code if code in THEMES else DEFAULT_THEME


def palette() -> dict:
    """返回当前主题的配色字典。"""
    return THEMES[_current]["palette"]


_STARFIELD_PATH = ""


def _starfield_image() -> str:
    """生成确定性的小星星背景 PNG，星空主题复用同一张图。"""
    global _STARFIELD_PATH
    if _STARFIELD_PATH and os.path.isfile(_STARFIELD_PATH):
        return _STARFIELD_PATH
    from PySide6.QtCore import QRandomGenerator, Qt
    from PySide6.QtGui import QColor, QImage, QPainter

    size = 512
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    rng = QRandomGenerator(20261120)
    for _ in range(150):
        x, y = int(rng.bounded(size)), int(rng.bounded(size))
        radius = 1 if rng.bounded(10) else 2
        painter.setBrush(QColor(205, 222, 255, 85 + rng.bounded(130)))
        painter.drawEllipse(x, y, radius, radius)
    for _ in range(9):
        x, y = int(rng.bounded(size)), int(rng.bounded(size))
        painter.setBrush(QColor(150, 190, 255, 26))
        painter.drawEllipse(x - 7, y - 7, 14, 14)
        painter.setBrush(QColor(255, 255, 255, 205))
        painter.drawEllipse(x - 1, y - 1, 2, 2)
    painter.end()
    path = os.path.join(tempfile.gettempdir(), "cxvc_starfield.png")
    image.save(path)
    _STARFIELD_PATH = path
    return path


def build_stylesheet(code: str | None = None) -> str:
    """生成可设置到 QApplication 的全局样式表。"""
    key = code if code in THEMES else _current
    p = THEMES[key]["palette"]
    extra_css = THEMES[key].get("extra_css", "")
    star_css = ""
    if THEMES[key].get("starfield"):
        try:
            url = _starfield_image().replace("\\", "/")
            star_css = f"\n    QWidget {{ background-image: url('{url}'); background-repeat: repeat; }}"
        except Exception:
            star_css = ""  # 背景生成失败时退回纯色星空底色
    return f"""
    QWidget {{ background: {p['bg']}; color: {p['text']}; font-family: 'Microsoft YaHei', 'Segoe UI'; font-size: 12px; }}
    QMainWindow::separator {{ background: {p['border']}; width: 4px; height: 4px; }}
    QToolBar {{ background: {p['toolbar']}; border-bottom: 1px solid {p['border']}; spacing: 6px; padding: 4px; }}
    QPushButton {{ background: {p['panel_alt']}; border: 1px solid {p['border']}; border-radius: 5px; padding: 5px 10px; color: {p['text']}; }}
    QPushButton:hover {{ background: {p['border']}; border-color: {p['accent']}; }}
    QPushButton:disabled {{ background: {p['panel']}; color: {p['muted']}; border-color: {p['border']}; }}
    QPushButton#primaryButton {{ background: {p['accent']}; border-color: {p['accent_hover']}; color: {p['accent_text']}; font-weight: bold; }}
    QPushButton#primaryButton:hover {{ background: {p['accent_hover']}; }}
    QLineEdit, QComboBox {{ background: {p['input']}; border: 1px solid {p['border']}; border-radius: 5px; padding: 4px 6px; color: {p['text']}; selection-background-color: {p['accent']}; }}
    QComboBox::drop-down {{ border: none; }}
    QComboBox QAbstractItemView {{ background: {p['menu']}; color: {p['text']}; border: 1px solid {p['border']}; }}
    QCheckBox, QRadioButton {{ color: {p['text']}; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1px solid {p['border']}; border-radius: 3px; background: {p['input']}; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {p['accent']}; border-color: {p['accent_hover']}; }}
    /* QTreeWidget 的勾选指示器在 macOS 上必须显式指定样式，否则原生样式不绘制 */
    QTreeWidget::indicator {{ width: 14px; height: 14px; border: 1px solid {p['border']}; border-radius: 3px; background: {p['input']}; }}
    QTreeWidget::indicator:checked {{ background: {p['accent']}; border-color: {p['accent_hover']}; }}
    QTreeWidget::indicator:unchecked:hover {{ border-color: {p['accent']}; }}
    QSlider::groove:horizontal {{ background: {p['border']}; height: 4px; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {p['accent']}; width: 12px; margin: -4px 0; border-radius: 6px; }}
    QTreeWidget, QListWidget {{ background: {p['panel']}; border: 1px solid {p['border']}; border-radius: 5px; }}
    QTreeWidget::item, QListWidget::item {{ padding: 3px; }}
    QHeaderView::section {{ background: {p['panel_alt']}; color: {p['text_soft']}; border: none; padding: 4px; }}
    QProgressBar {{ background: {p['input']}; border: 1px solid {p['border']}; border-radius: 5px; height: 16px; text-align: center; color: {p['text']}; }}
    QProgressBar::chunk {{ background: {p['progress']}; border-radius: 4px; }}
    QMenuBar {{ background: {p['toolbar']}; color: {p['text']}; }}
    QMenuBar::item:selected {{ background: {p['border']}; }}
    QMenu {{ background: {p['menu']}; border: 1px solid {p['border']}; color: {p['text']}; }}
    QMenu::item:selected {{ background: {p['accent']}; color: {p['accent_text']}; }}
    QStatusBar {{ background: {p['toolbar']}; color: {p['muted']}; }}
    QToolTip {{ background: {p['menu']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 3px; }}
    QScrollBar:horizontal {{ background: {p['panel']}; height: 10px; }}
    QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 5px; min-width: 24px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QWidget#vsep {{ background: {p['muted']}; border-radius: 1px; }}
    QLabel[muted="true"] {{ color: {p['muted']}; font-size: 11px; }}
    QLabel[small="true"] {{ color: {p['text_soft']}; font-size: 11px; }}
    QLabel[hint="true"] {{ color: {p['muted']}; font-size: 12px; padding: 24px; }}
    QLabel[sectionTitle="true"] {{ font-weight: bold; font-size: 13px; color: {p['text_strong']}; }}
    QLabel[itemTitle="true"] {{ font-weight: bold; font-size: 12px; color: {p['text_strong']}; }}
    QWidget#preview {{ background: #000000; border: 1px solid {p['border']}; border-radius: 5px; }}
    QFrame#segmentItem {{ background: {p['panel_alt']}; border: 1px solid {p['border']}; border-radius: 6px; }}
    QFrame#segmentItem:hover {{ border: 1px solid {p['accent']}; }}
    QLabel#thumb {{ background: {p['bg']}; border: 1px solid {p['border']}; border-radius: 3px; }}
    QListWidget#transparent {{ background: transparent; border: none; }}
    {extra_css}
    {star_css}
    """


def apply_theme(app, code: str, ui_metrics=None) -> None:
    """设置当前主题并应用到全局（主窗口与所有对话框）。

    ui_metrics 可选，传入时用其缩放系数生成样式表；不传则用全局 Metrics。
    """
    set_theme(code)
    p = palette()
    # 音量条保持设计时的固定尺寸，不随界面缩放变大。
    volume_fixed = f"""
QSlider#volumeSlider::groove:horizontal {{ background: {p['border']}; height: 4px; border-radius: 2px; }}
QSlider#volumeSlider::handle:horizontal {{ background: {p['accent']}; width: 12px; margin: -4px 0; border-radius: 6px; }}
"""
    # scale_stylesheet 读取 ui_scale 的全局 Metrics；ui_metrics 参数仅为
    # 与 CXPurePlayer 风格的调用保持一致，真正的尺寸源是全局单例。
    app.setStyleSheet(scale_stylesheet(build_stylesheet(code), volume_fixed))
