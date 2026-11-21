"""日志查看对话框：按日期列出日志并展示内容。"""

from __future__ import annotations

import os
from datetime import date
from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView,
    QLabel, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from ..core.i18n import tr
from ..core.logger import cleanup_old_logs, log_dir
from .msgbox import show_warning


class LogViewDialog(QDialog):
    """只读展示单个日志文件。"""

    def __init__(self, path: str, day: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('日志')} - {day}")
        self.resize(820, 560)
        layout = QVBoxLayout(self)

        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.setCenterButtons(True)
        self.btn_close = buttons.button(QDialogButtonBox.StandardButton.Close)
        if self.btn_close is not None:
            self.btn_close.setText(tr("关闭"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                self.text.setPlainText(handle.read())
        except OSError as exc:
            self.text.setPlainText(f"{tr('读取日志失败')}: {exc}")


class LogDialog(QDialog):
    """日志列表，按日期倒序排列。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("日志"))
        self.resize(720, 420)
        self._paths: List[str] = []
        self._view_buttons: List[QPushButton] = []

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels([tr("日期"), tr("大小"), tr("操作")])
        header = self.table.horizontalHeader()
        # 三列等宽：关闭末列拉伸，全部使用 Stretch 平分配表宽度
        header.setStretchLastSection(False)
        for column in range(3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel(tr("无日志文件"), self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.setCenterButtons(True)
        self.btn_close = buttons.button(QDialogButtonBox.StandardButton.Close)
        if self.btn_close is not None:
            self.btn_close.setText(tr("关闭"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._reload()

    def _reload(self) -> None:
        cleanup_old_logs(30)
        directory = log_dir()
        entries: List[Tuple[date, str, str, int]] = []
        if os.path.isdir(directory):
            for name in os.listdir(directory):
                if not name.endswith(".log"):
                    continue
                try:
                    day = date.fromisoformat(name[:-4])
                except ValueError:
                    continue
                path = os.path.join(directory, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                entries.append((day, name[:-4], path, size))
        entries.sort(key=lambda item: item[0], reverse=True)

        self._paths = [item[2] for item in entries]
        self._view_buttons = []
        self.table.setRowCount(len(entries))
        for row, (_day, label, path, size) in enumerate(entries):
            self.table.setItem(row, 0, QTableWidgetItem(label))
            self.table.setItem(row, 1, QTableWidgetItem(f"{size / 1024:.1f} KB"))
            button = QPushButton(tr("查看"), self)
            button.clicked.connect(
                lambda _checked=False, p=path, d=label: self._view(p, d)
            )
            self.table.setCellWidget(row, 2, button)
            self._view_buttons.append(button)

        self.empty_label.setVisible(not entries)
        self.table.setVisible(bool(entries))

    def _on_double_click(self, index) -> None:
        row = index.row()
        if 0 <= row < len(self._paths):
            label = self.table.item(row, 0).text()
            self._view(self._paths[row], label)

    def _view(self, path: str, day: str) -> None:
        dialog = LogViewDialog(path, day, self)
        dialog.exec()

    def retranslate(self) -> None:
        self.setWindowTitle(tr("日志"))
        self.table.setHorizontalHeaderLabels([tr("日期"), tr("大小"), tr("操作")])
        self.empty_label.setText(tr("无日志文件"))
        if self.btn_close is not None:
            self.btn_close.setText(tr("关闭"))
        for button in self._view_buttons:
            button.setText(tr("查看"))
