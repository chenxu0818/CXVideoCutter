"""CXVideoCutter - 程序入口。"""

import os
import sys

# 保证从任意目录启动都能找到 app 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _enable_dpi_awareness() -> None:
    """必须在创建任何 Qt 对象前声明 DPI 感知。

    PyInstaller 单文件程序若未显式声明，Windows 会把它当作 DPI 未感知进程，
    Qt 只能拿到 96 DPI，导致高分屏上图标、按钮、文字都偏小。
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE_V2 = -4
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE_V2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_enable_dpi_awareness()

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.logger import cleanup_old_logs  # noqa: E402
from app.core.settings import AppSettings  # noqa: E402
from app.core.theme import apply_theme  # noqa: E402
from app.core.ui_scale import apply as apply_ui_scale  # noqa: E402
from app.ui.app_icon import app_icon  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.version import APP_VERSION  # noqa: E402


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    app.setApplicationName("CXVideoCutter")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("CXVideoCutter")
    cleanup_old_logs(30)
    settings = AppSettings()
    apply_ui_scale(settings.ui_scale())
    apply_theme(app, settings.theme())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
