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

    def ui_scale_mode(self) -> str:
        """界面缩放模式：auto（按屏幕分辨率自动）/ manual（手动百分比）。"""
        raw = self._settings.value("ui_scale_mode", "", str) or ""
        if raw in ("auto", "manual"):
            return raw
        # 兼容 v1.0.1 及之前的 ui_scale 字符串：auto 或 0.9/1.0/1.25/...
        old = self._settings.value("ui_scale", "auto", str) or "auto"
        return "auto" if old == "auto" else "manual"

    def set_ui_scale_mode(self, mode: str) -> None:
        self._settings.setValue("ui_scale_mode", "manual" if mode == "manual" else "auto")
        self._settings.sync()

    def ui_scale_percent(self) -> int:
        """手动缩放百分比，范围 80~200。"""
        raw = self._settings.value("ui_scale_percent", "", str) or ""
        if not raw:
            old = self._settings.value("ui_scale", "auto", str) or "auto"
            if old == "auto":
                return 100
            try:
                return int(round(float(old) * 100))
            except (TypeError, ValueError):
                return 100
        try:
            return max(80, min(200, int(raw)))
        except (TypeError, ValueError):
            return 100

    def set_ui_scale_percent(self, value: int) -> None:
        self._settings.setValue("ui_scale_percent", max(80, min(200, int(value))))
        self._settings.sync()

    def ui_scale(self) -> str:
        """兼容旧接口：返回 auto 或形如 '1.25' 的比例字符串。"""
        if self.ui_scale_mode() == "auto":
            return "auto"
        return str(round(self.ui_scale_percent() / 100.0, 2))

    def set_ui_scale(self, value: str) -> None:
        """兼容旧接口：设置自动或固定比例。"""
        if value == "auto":
            self.set_ui_scale_mode("auto")
            return
        try:
            self.set_ui_scale_percent(int(round(float(value) * 100)))
            self.set_ui_scale_mode("manual")
        except (TypeError, ValueError):
            self.set_ui_scale_mode("auto")

    def window_geometry(self) -> str:
        """上次退出时的窗口几何，空字符串表示尚未保存。"""
        return self._settings.value("window_geometry", "", str) or ""

    def set_window_geometry(self, value: str) -> None:
        self._settings.setValue("window_geometry", value)
        self._settings.sync()
