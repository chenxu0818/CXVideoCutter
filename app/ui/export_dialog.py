"""导出设置对话框（由右上角导出按钮弹出）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from ..core.ui_scale import ui_px
from ..core.i18n import tr
from .app_icon import app_icon


class ExportDialog(QDialog):
    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self._busy = False
        self.setWindowTitle(tr("导出设置"))
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(ui_px(500))
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.addWidget(panel)

        # 关闭按钮居中放置
        self.close_button = QPushButton(tr("关闭"))
        self.close_button.setFixedWidth(ui_px(100))
        self.close_button.clicked.connect(self.hide)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_button)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

    def setBusy(self, busy: bool) -> None:  # noqa: N802
        """导出期间禁止关闭对话框（含右上角 X），结束后恢复。"""
        self._busy = busy
        self.close_button.setEnabled(not busy)
        flags = self.windowFlags()
        if busy:
            flags &= ~Qt.WindowType.WindowCloseButtonHint
        else:
            flags |= Qt.WindowType.WindowCloseButtonHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()   # 某些平台修改 flags 后窗口会被隐藏

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._busy:
            event.ignore()
        else:
            event.accept()

    def retranslate(self) -> None:
        self.setWindowTitle(tr("导出设置"))
        self.close_button.setText(tr("关闭"))
