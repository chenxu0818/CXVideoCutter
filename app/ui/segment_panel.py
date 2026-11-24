"""右侧片段列表面板：首帧画面、开始、结束、时长。"""

from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from ..core.ui_scale import ui_px
from ..core.ffmpeg import format_time
from ..core.i18n import tr
from ..core.models import Segment


class _SegmentItem(QFrame):
    removeClicked = Signal(int)
    locateClicked = Signal(int)

    def __init__(self, segment: Segment, index: int, parent=None):
        super().__init__(parent)
        self.segment = segment
        self.index = index
        self.setObjectName("segmentItem")

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(ui_px(96), ui_px(54))
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setText(tr("无预览"))
        root.addWidget(self.thumb)

        info = QVBoxLayout()
        info.setSpacing(2)
        self.title = QLabel(f"{tr('片段 ')}{index + 1}")
        self.title.setProperty("itemTitle", True)
        info.addWidget(self.title)

        self.lbl_start = QLabel()
        self.lbl_end = QLabel()
        self.lbl_duration = QLabel()
        for lbl in (self.lbl_start, self.lbl_end, self.lbl_duration):
            lbl.setProperty("small", True)
        info.addWidget(self.lbl_start)
        info.addWidget(self.lbl_end)
        info.addWidget(self.lbl_duration)
        info.addStretch(1)
        root.addLayout(info, 1)

        btns = QVBoxLayout()
        btns.setSpacing(4)
        self.btn_locate = QPushButton(tr("定位"))
        self.btn_locate.setFixedWidth(ui_px(44))
        self.btn_remove = QPushButton(tr("删除"))
        self.btn_remove.setFixedWidth(ui_px(44))
        self.btn_locate.clicked.connect(lambda: self.locateClicked.emit(self.segment.id))
        self.btn_remove.clicked.connect(lambda: self.removeClicked.emit(self.segment.id))
        btns.addWidget(self.btn_locate)
        btns.addWidget(self.btn_remove)
        btns.addStretch(1)
        root.addLayout(btns)
        self.refresh()
        # 列表在新增/删除片段时会整体重建，必须把已经异步加载好的缩略图恢复回来
        if segment.thumbnail and os.path.isfile(segment.thumbnail):
            self.setThumbnail(segment.thumbnail)

    def refresh(self) -> None:
        s = self.segment
        self.lbl_start.setText(f"{tr('开始  ')}{format_time(s.start)}")
        self.lbl_end.setText(f"{tr('结束  ')}{format_time(s.end)}")
        self.lbl_duration.setText(f"{tr('时长  ')}{format_time(s.duration)}")

    def retranslate(self) -> None:
        self.title.setText(f"{tr('片段 ')}{self.index + 1}")
        self.btn_locate.setText(tr("定位"))
        self.btn_remove.setText(tr("删除"))
        if self.thumb.pixmap() is None:
            self.thumb.setText(tr("无预览"))
        self.refresh()

    def setThumbnail(self, path: str) -> None:  # noqa: N802
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self.thumb.setPixmap(pixmap.scaled(
            self.thumb.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        self.thumb.setText("")


class SegmentPanel(QWidget):
    """片段列表容器。"""

    removeRequested = Signal(int)
    locateRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: List[Segment] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self.title = QLabel(tr("已选片段"))
        self.title.setProperty("sectionTitle", True)
        self.count_label = QLabel(f"{tr('共 ')}0{tr(' 段')}")
        self.count_label.setProperty("muted", True)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        root.addLayout(header)

        self.list = QListWidget()
        self.list.setObjectName("transparent")
        self.list.setSpacing(4)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        root.addWidget(self.list)

        self.empty = QLabel(tr("在左侧设置入点 / 出点后点击\n“添加片段”，或在时间轴上拖拽选择"))
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setProperty("hint", True)
        root.addWidget(self.empty)

    # ------------------------------------------------------------------
    def setSegments(self, segments: List[Segment]) -> None:  # noqa: N802
        self._segments = segments
        self.list.clear()
        for i, seg in enumerate(segments):
            item = QListWidgetItem(self.list)
            widget = _SegmentItem(seg, i, self.list)
            widget.removeClicked.connect(self.removeRequested.emit)
            widget.locateClicked.connect(self.locateRequested.emit)
            item.setSizeHint(widget.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, widget)
        self.count_label.setText(f"{tr('共 ')}{len(segments)}{tr(' 段')}")
        self.empty.setVisible(len(segments) == 0)
        self.list.setVisible(len(segments) > 0)

    def retranslate(self) -> None:
        self.title.setText(tr("已选片段"))
        self.count_label.setText(f"{tr('共 ')}{len(self._segments)}{tr(' 段')}")
        self.empty.setText(tr("在左侧设置入点 / 出点后点击\n“添加片段”，或在时间轴上拖拽选择"))
        for i in range(self.list.count()):
            widget = self.list.itemWidget(self.list.item(i))
            if isinstance(widget, _SegmentItem):
                widget.retranslate()

    def updateThumbnail(self, seg_id: int, path: str) -> None:  # noqa: N802
        for i in range(self.list.count()):
            widget = self.list.itemWidget(self.list.item(i))
            if isinstance(widget, _SegmentItem) and widget.segment.id == seg_id:
                widget.setThumbnail(path)
                break
