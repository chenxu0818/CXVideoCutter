"""统一消息框：按钮文字显式跟随界面语言，并居中显示。

Qt 的 QMessageBox.information()/warning()/about() 静态方法会使用 Qt 自带的
按钮文字（通常为英文 OK），不受本程序 i18n 控制；同时按钮默认靠右。这里统一
用 NoButton + 手动添加本地化按钮，并开启 QDialogButtonBox 的居中布局。
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialogButtonBox, QMessageBox, QWidget

from ..core.i18n import tr


def _make_box(
    parent: QWidget | None, icon: QMessageBox.Icon, title: str, text: str
) -> QMessageBox:
    box = QMessageBox(icon, title, text, QMessageBox.StandardButton.NoButton, parent)
    button_box = box.findChild(QDialogButtonBox)
    if button_box is not None:
        button_box.setCenterButtons(True)
    return box


def show_info(parent: QWidget | None, title: str, text: str) -> None:
    box = _make_box(parent, QMessageBox.Icon.Information, title, text)
    ok = box.addButton(tr("确定"), QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(ok)
    box.exec()


def show_warning(parent: QWidget | None, title: str, text: str) -> None:
    box = _make_box(parent, QMessageBox.Icon.Warning, title, text)
    ok = box.addButton(tr("确定"), QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(ok)
    box.exec()


def ask_yes_no(parent: QWidget | None, text: str, title: str | None = None) -> bool:
    box = _make_box(
        parent, QMessageBox.Icon.Question, title or tr("提示"), text
    )
    btn_yes = box.addButton(tr("是"), QMessageBox.ButtonRole.YesRole)
    btn_no = box.addButton(tr("否"), QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(btn_no)
    box.exec()
    return box.clickedButton() is btn_yes


def show_about(parent: QWidget | None, title: str, text: str) -> None:
    """关于对话框：同样使用本地化「确定」按钮并居中。"""
    show_info(parent, title, text)
