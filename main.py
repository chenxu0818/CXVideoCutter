"""CXVideoCutter - 程序入口。"""

import os
import sys

# 保证从任意目录启动都能找到 app 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.logger import cleanup_old_logs  # noqa: E402
from app.core.settings import AppSettings  # noqa: E402
from app.core.theme import apply_theme  # noqa: E402
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
    apply_theme(app, AppSettings().theme())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
