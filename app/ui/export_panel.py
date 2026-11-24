"""导出设置面板：导出方式、分辨率、格式、输出目录与进度。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QProgressBar, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

from ..core.ui_scale import ui_px
from ..core.i18n import tr
from ..core.models import ExportSettings

RES_LABELS = [
    "原分辨率（无损，不重编码）",
    "720p（H264 重编码）",
    "1080p（H264 重编码）",
    "4K（H264 重编码）",
]
FORMAT_LABELS = ["原视频格式", "MKV", "MP4"]


class ExportPanel(QWidget):
    exportRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = ExportSettings()
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        self.title = QLabel(tr("导出设置"))
        self.title.setProperty("sectionTitle", True)
        root.addWidget(self.title)

        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.mode_widget = QWidget()
        mode_layout = QHBoxLayout(self.mode_widget)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        self.rb_separate = QRadioButton(tr("多段分别导出"))
        self.rb_merge = QRadioButton(tr("合并导出"))
        self.rb_merge.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.rb_separate)
        group.addButton(self.rb_merge)
        mode_layout.addWidget(self.rb_separate)
        mode_layout.addWidget(self.rb_merge)
        self.form.addRow(tr("导出方式"), self.mode_widget)

        self.combo_res = QComboBox()
        self.combo_res.addItems([tr(t) for t in RES_LABELS])
        self.combo_res.currentIndexChanged.connect(self._update_settings)
        self.form.addRow(tr("分辨率"), self.combo_res)

        self.combo_format = QComboBox()
        self.combo_format.addItems([tr(t) for t in FORMAT_LABELS])
        self.combo_format.currentIndexChanged.connect(self._update_settings)
        self.form.addRow(tr("导出格式"), self.combo_format)

        self.dir_widget = QWidget()
        dir_layout = QHBoxLayout(self.dir_widget)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_dir = QLineEdit()
        self.edit_dir.setPlaceholderText(tr("选择导出目录"))
        self.btn_browse = QPushButton(tr("浏览…"))
        self.btn_browse.setFixedWidth(ui_px(64))
        dir_layout.addWidget(self.edit_dir, 1)
        dir_layout.addWidget(self.btn_browse)
        self.btn_browse.clicked.connect(self._browse)
        self.form.addRow(tr("输出目录"), self.dir_widget)
        root.addLayout(self.form)

        self.info = QLabel()
        self.info.setProperty("muted", True)
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        action = QHBoxLayout()
        self.btn_export = QPushButton(tr("开始导出"))
        self.btn_export.setObjectName("primaryButton")
        self.btn_cancel = QPushButton(tr("取消"))
        self.btn_cancel.setEnabled(False)
        self.btn_export.clicked.connect(self.exportRequested.emit)
        self.btn_cancel.clicked.connect(self.cancelRequested.emit)
        action.addWidget(self.btn_export, 1)
        action.addWidget(self.btn_cancel)
        root.addLayout(action)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.status = QLabel(tr("就绪"))
        self.status.setProperty("muted", True)
        root.addWidget(self.status)
        self._update_settings()

    # ------------------------------------------------------------------
    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, tr("选择输出目录"), self.edit_dir.text())
        if path:
            self.edit_dir.setText(path)
            self._update_settings()

    def _update_settings(self, *args) -> None:
        self.settings.mode = "merge" if self.rb_merge.isChecked() else "separate"
        self.settings.resolution = ["original", "720p", "1080p", "4k"][self.combo_res.currentIndex()]
        self.settings.container = ["original", "mkv", "mp4"][self.combo_format.currentIndex()]
        self.settings.output_dir = self.edit_dir.text()
        self.info.setText(tr("原分辨率将直接复制视频流，剪辑速度最快且画质无损。")
                          if self.settings.resolution == "original" else
                          tr("非原分辨率：视频流将使用 H.264 重新编码，音频保持复制。"))

    def setBusy(self, busy: bool) -> None:  # noqa: N802
        self.btn_export.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        # 导出期间锁定所有设置项，避免参数在任务进行中被改动导致结果不一致
        for widget in (
            self.rb_separate, self.rb_merge, self.combo_res,
            self.combo_format, self.edit_dir, self.btn_browse,
        ):
            widget.setEnabled(not busy)

    def setProgress(self, value: int, message: str) -> None:  # noqa: N802
        self.progress.setValue(value)
        self.status.setText(message)

    def reset(self) -> None:
        self.setBusy(False)
        self.progress.setValue(0)
        self.status.setText(tr("就绪"))

    def setOutputDir(self, path: str) -> None:  # noqa: N802
        self.edit_dir.setText(path)
        self._update_settings()

    def retranslate(self) -> None:
        self.title.setText(tr("导出设置"))
        labels = [
            (self.mode_widget, tr("导出方式")),
            (self.combo_res, tr("分辨率")),
            (self.combo_format, tr("导出格式")),
            (self.dir_widget, tr("输出目录")),
        ]
        for widget, text in labels:
            label = self.form.labelForField(widget)
            if label is not None:
                label.setText(text)
        self.rb_separate.setText(tr("多段分别导出"))
        self.rb_merge.setText(tr("合并导出"))
        for i, item in enumerate(RES_LABELS):
            self.combo_res.setItemText(i, tr(item))
        for i, item in enumerate(FORMAT_LABELS):
            self.combo_format.setItemText(i, tr(item))
        self.edit_dir.setPlaceholderText(tr("选择导出目录"))
        self.btn_browse.setText(tr("浏览…"))
        self.btn_export.setText(tr("开始导出"))
        self.btn_cancel.setText(tr("取消"))
        self._update_settings()
        if self.status.text() == tr("就绪"):
            self.status.setText(tr("就绪"))
