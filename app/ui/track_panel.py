"""轨道与章节面板：启用/禁用轨道、添加外部音轨与字幕、管理章节。"""

from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from ..core.ffmpeg import format_time
from ..core.i18n import tr
from ..core.models import Chapter, MediaSource, StreamInfo


class TrackPanel(QWidget):
    """轨道管理与章节管理。"""

    addExternalRequested = Signal(str)        # "audio" / "subtitle"
    removeTrackRequested = Signal(int, int)   # input_index, stream_index
    addChapterRequested = Signal()
    removeChapterRequested = Signal(int)
    chapterSelected = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sources: List[MediaSource] = []
        self.chapters: List[Chapter] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # ---- 轨道 ----
        head = QHBoxLayout()
        self.label_tracks = QLabel(tr("轨道管理"))
        head.addWidget(self.label_tracks)
        head.addStretch(1)
        self.btn_all_on = QPushButton(tr("全选"))
        self.btn_all_off = QPushButton(tr("全不选"))
        self.btn_all_on.setFixedWidth(48)
        self.btn_all_off.setFixedWidth(58)
        self.btn_all_on.clicked.connect(lambda: self.setAll(True))
        self.btn_all_off.clicked.connect(lambda: self.setAll(False))
        head.addWidget(self.btn_all_on)
        head.addWidget(self.btn_all_off)
        root.addLayout(head)

        self._refreshing = False
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("选择"), tr("轨道（勾选表示导出该轨道）")])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 46)
        self.tree.setIndentation(12)
        self.tree.setRootIsDecorated(True)
        self.tree.itemChanged.connect(self._on_toggle)
        root.addWidget(self.tree, 3)

        btns = QHBoxLayout()
        self.btn_audio = QPushButton(tr("+ 音轨"))
        self.btn_sub = QPushButton(tr("+ 字幕"))
        self.btn_remove_track = QPushButton(tr("移除轨道"))
        self.btn_audio.clicked.connect(lambda: self.addExternalRequested.emit("audio"))
        self.btn_sub.clicked.connect(lambda: self.addExternalRequested.emit("subtitle"))
        self.btn_remove_track.clicked.connect(self._remove_track)
        btns.addWidget(self.btn_audio)
        btns.addWidget(self.btn_sub)
        btns.addWidget(self.btn_remove_track)
        root.addLayout(btns)

        # ---- 章节 ----
        chapter_head = QHBoxLayout()
        self.label_chapters = QLabel(tr("章节"))
        chapter_head.addWidget(self.label_chapters)
        chapter_head.addStretch(1)
        self.btn_add_chapter = QPushButton(tr("+ 当前时间"))
        self.btn_del_chapter = QPushButton(tr("删除"))
        self.btn_add_chapter.clicked.connect(self.addChapterRequested.emit)
        self.btn_del_chapter.clicked.connect(self._remove_chapter)
        chapter_head.addWidget(self.btn_add_chapter)
        chapter_head.addWidget(self.btn_del_chapter)
        root.addLayout(chapter_head)

        self.chapter_list = QListWidget()
        self.chapter_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.chapter_list.itemDoubleClicked.connect(
            lambda item: self.chapterSelected.emit(float(item.data(Qt.ItemDataRole.UserRole)))
        )
        self.chapter_list.setMinimumHeight(70)
        root.addWidget(self.chapter_list, 2)

    # ------------------------------------------------------------------
    def setData(self, sources: List[MediaSource], chapters: List[Chapter]) -> None:  # noqa: N802
        self.sources = sources
        self.chapters = chapters
        self.refresh()

    def refresh(self) -> None:
        self._refreshing = True   # 避免程序化设置勾选状态触发 _on_toggle
        self.tree.clear()
        for src in self.sources:
            prefix = tr("主视频：") if src.input_index == 0 else tr("外部：")
            src_item = QTreeWidgetItem([prefix + os.path.basename(src.path), ""])
            src_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for stream in src.streams:
                item = QTreeWidgetItem()
                item.setText(1, stream.label())
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsSelectable
                )
                item.setCheckState(
                    0, Qt.CheckState.Checked if stream.enabled else Qt.CheckState.Unchecked
                )
                item.setData(0, Qt.ItemDataRole.UserRole, (stream.input_index, stream.index))
                src_item.addChild(item)
            self.tree.addTopLevelItem(src_item)
            src_item.setExpanded(True)
        self._refreshing = False

        self.chapter_list.clear()
        for i, ch in enumerate(self.chapters):
            item = QListWidgetItem(f"{i + 1}. {format_time(ch.time)}   {ch.title or tr('（无标题）')}")
            item.setData(Qt.ItemDataRole.UserRole, ch.time)
            self.chapter_list.addItem(item)

    # ------------------------------------------------------------------
    def _on_toggle(self, item: QTreeWidgetItem, column: int) -> None:
        if self._refreshing or column != 0 or item.parent() is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        ii, si = data
        enabled = item.checkState(0) == Qt.CheckState.Checked
        for src in self.sources:
            for stream in src.streams:
                if stream.input_index == ii and stream.index == si:
                    stream.enabled = enabled
                    return

    def _remove_track(self) -> None:
        current = self.tree.currentItem()
        if current is None or current.parent() is None:
            return
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        self.removeTrackRequested.emit(int(data[0]), int(data[1]))

    def _remove_chapter(self) -> None:
        row = self.chapter_list.currentRow()
        if row >= 0:
            self.removeChapterRequested.emit(row)

    def setAll(self, enabled: bool) -> None:  # noqa: N802
        for src in self.sources:
            for stream in src.streams:
                stream.enabled = enabled
        self.refresh()

    def retranslate(self) -> None:
        self.label_tracks.setText(tr("轨道管理"))
        self.btn_all_on.setText(tr("全选"))
        self.btn_all_off.setText(tr("全不选"))
        self.tree.setHeaderLabels([tr("选择"), tr("轨道（勾选表示导出该轨道）")])
        self.btn_audio.setText(tr("+ 音轨"))
        self.btn_sub.setText(tr("+ 字幕"))
        self.btn_remove_track.setText(tr("移除轨道"))
        self.label_chapters.setText(tr("章节"))
        self.btn_add_chapter.setText(tr("+ 当前时间"))
        self.btn_del_chapter.setText(tr("删除"))
        self.refresh()
