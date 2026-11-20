"""应用配置：输出目录、界面语言、主题。"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QSettings

from .theme import DEFAULT_THEME


def app_root() -> str:
    """返回可写的应用数据目录。

    Windows：源码模式用项目根目录，打包后按 dist/EXE 目录处理；
    macOS：打包成 .app 后可执行目录位于只读 bundle 内，改用
           ~/Library/Application Support/CXVideoCutter。
    """
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        base = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", "CXVideoCutter"
        )
        os.makedirs(base, exist_ok=True)
        return base
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.basename(exe_dir).lower() == "dist":
            return os.path.dirname(exe_dir)
        return exe_dir
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def default_output_dir() -> str:
    if sys.platform == "darwin":
        movies = os.path.join(os.path.expanduser("~"), "Movies")
        return os.path.join(movies if os.path.isdir(movies) else os.path.expanduser("~"),
                            "CXVideoCutter")
    return os.path.join(app_root(), "output")


class AppSettings:
    """基于 ini 文件的持久化设置。"""

    def __init__(self):
        self._settings = QSettings(os.path.join(app_root(), "settings.ini"),
                                   QSettings.Format.IniFormat)

    def output_dir(self) -> str:
        value = self._settings.value("output_dir", "", str)
        return value or default_output_dir()

    def set_output_dir(self, path: str) -> None:
        self._settings.setValue("output_dir", path)
        self._settings.sync()

    def language(self) -> str:
        return self._settings.value("language", "zh_CN", str) or "zh_CN"

    def set_language(self, code: str) -> None:
        self._settings.setValue("language", code)
        self._settings.sync()

    def theme(self) -> str:
        return self._settings.value("theme", DEFAULT_THEME, str) or DEFAULT_THEME

    def set_theme(self, code: str) -> None:
        self._settings.setValue("theme", code)
        self._settings.sync()

    def allow_segment_overlap(self) -> bool:
        """是否允许片段之间重复 / 交叠，默认允许。"""
        return self._settings.value("allow_segment_overlap", True, bool)

    def set_allow_segment_overlap(self, value: bool) -> None:
        self._settings.setValue("allow_segment_overlap", bool(value))
        self._settings.sync()
