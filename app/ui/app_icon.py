"""应用图标加载：兼容源码运行与 PyInstaller 单文件打包。"""

from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon

_ICON_REL = os.path.join("app", "resources", "icon.ico")


def app_icon() -> QIcon:
    """返回应用图标；找不到时返回空图标（不影响功能）。"""
    roots = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(meipass)
    source_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    roots.append(source_root)
    roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    for root in roots:
        path = os.path.join(root, _ICON_REL)
        if os.path.isfile(path):
            return QIcon(path)
    return QIcon()
