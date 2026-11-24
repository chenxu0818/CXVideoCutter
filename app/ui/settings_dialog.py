"""设置对话框：保存目录与界面语言。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..core.i18n import LANGUAGES, tr
from ..core.theme import THEME_CHOICES
from ..core.ui_scale import SCALE_CHOICES, ui_px
from .app_icon import app_icon


class SettingsDialog(QDialog):
    def __init__(
        self, output_dir: str, language: str, theme: str = "default",
        allow_overlap: bool = True, ui_scale: str = "auto", parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("设置…"))
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(ui_px(520))

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.label_lang = QLabel(tr("界面语言"))
        self.combo_lang = QComboBox()
        for code, name in LANGUAGES:
            self.combo_lang.addItem(name, code)
        index = self.combo_lang.findData(language)
        if index >= 0:
            self.combo_lang.setCurrentIndex(index)
        form.addRow(self.label_lang, self.combo_lang)

        self.label_theme = QLabel(tr("主题"))
        self.combo_theme = QComboBox()
        for code, name in THEME_CHOICES:
            self.combo_theme.addItem(tr(name), code)
        index = self.combo_theme.findData(theme)
        if index >= 0:
            self.combo_theme.setCurrentIndex(index)
        form.addRow(self.label_theme, self.combo_theme)

        self.label_scale = QLabel(tr("界面缩放"))
        self.combo_scale = QComboBox()
        for code, name in SCALE_CHOICES:
            self.combo_scale.addItem(tr(name), code)
        index = self.combo_scale.findData(ui_scale)
        if index >= 0:
            self.combo_scale.setCurrentIndex(index)
        self.combo_scale.setToolTip(tr("界面缩放提示"))
        form.addRow(self.label_scale, self.combo_scale)

        self.chk_allow_overlap = QCheckBox(tr("允许片段重叠"))
        self.chk_allow_overlap.setChecked(bool(allow_overlap))
        self.chk_allow_overlap.setToolTip(tr("关闭后，新片段不能与已有片段重复或重叠。"))
        form.addRow("", self.chk_allow_overlap)

        self.label_dir = QLabel(tr("视频保存目录"))
        dir_widget = QWidget()
        dir_widget.setLayout(QHBoxLayout())
        dir_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.edit_dir = QLineEdit(output_dir)
        self.btn_browse = QPushButton(tr("浏览…"))
        self.btn_browse.clicked.connect(self._browse)
        dir_widget.layout().addWidget(self.edit_dir, 1)
        dir_widget.layout().addWidget(self.btn_browse)
        form.addRow(self.label_dir, dir_widget)
        root.addLayout(form)

        self.hint = QLabel(tr("更改语言后立即生效，保存目录将在下次导出时使用。"))
        self.hint.setProperty("muted", True)
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_reset = QPushButton(tr("恢复默认"))
        self.btn_reset.clicked.connect(self._restore)
        self.btn_box.addButton(self.btn_reset, QDialogButtonBox.ButtonRole.ResetRole)
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        root.addWidget(self.btn_box)

        # QDialogButtonBox 的标准按钮默认跟随 Qt 语言包，这里显式按界面语言设置文本
        self.btn_ok = self.btn_box.button(QDialogButtonBox.StandardButton.Ok)
        self.btn_cancel = self.btn_box.button(QDialogButtonBox.StandardButton.Cancel)
        self._retranslate_buttons()

        self.default_dir = output_dir

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("选择输出目录"), self.edit_dir.text())
        if path:
            self.edit_dir.setText(path)

    def _restore(self) -> None:
        self.edit_dir.setText(self.default_dir)
        self.combo_lang.setCurrentIndex(0)
        self.combo_theme.setCurrentIndex(0)
        self.combo_scale.setCurrentIndex(0)
        self.chk_allow_overlap.setChecked(True)

    def values(self) -> tuple[str, str, str, bool, str]:
        return (
            self.edit_dir.text().strip(),
            self.combo_lang.currentData(),
            self.combo_theme.currentData(),
            self.chk_allow_overlap.isChecked(),
            self.combo_scale.currentData(),
        )

    def _retranslate_buttons(self) -> None:
        self.btn_ok.setText(tr("确定"))
        self.btn_cancel.setText(tr("取消"))

    def retranslate(self) -> None:
        self.setWindowTitle(tr("设置…"))
        self.label_lang.setText(tr("界面语言"))
        self.label_theme.setText(tr("主题"))
        self.label_scale.setText(tr("界面缩放"))
        self.combo_scale.setToolTip(tr("界面缩放提示"))
        self.chk_allow_overlap.setText(tr("允许片段重叠"))
        self.chk_allow_overlap.setToolTip(tr("关闭后，新片段不能与已有片段重复或重叠。"))
        self.label_dir.setText(tr("视频保存目录"))
        self.btn_browse.setText(tr("浏览…"))
        self.hint.setText(tr("更改语言后立即生效，保存目录将在下次导出时使用。"))
        self.btn_reset.setText(tr("恢复默认"))
        self._retranslate_buttons()
        for i, (_code, name) in enumerate(LANGUAGES):
            self.combo_lang.setItemText(i, name)
        for i, (_code, name) in enumerate(THEME_CHOICES):
            self.combo_theme.setItemText(i, tr(name))
        for i, (_code, name) in enumerate(SCALE_CHOICES):
            self.combo_scale.setItemText(i, tr(name))
