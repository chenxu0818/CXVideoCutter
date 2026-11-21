"""主窗口：预览、剪辑选段、轨道管理与导出。"""

from __future__ import annotations

import os
import tempfile
from fractions import Fraction
from typing import List

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QSizePolicy, QSlider, QSplitter,
    QStackedWidget, QToolBar, QVBoxLayout, QWidget,
)

from ..core.exporter import ExportWorker
from ..core.ffmpeg import format_time, probe_media, probe_version
from ..core.i18n import set_language, tr
from ..core.logger import cleanup_old_logs, log_error, log_info
from ..core.models import Chapter, MediaSource, Segment
from ..core.settings import AppSettings, default_output_dir
from ..core.taskbar_progress import TaskbarProgress
from ..core.theme import apply_theme
from ..version import APP_VERSION_TAG
from .app_icon import app_icon
from .export_dialog import ExportDialog
from .export_panel import ExportPanel
from .filmstrip import FilmstripLoader, FilmstripWidget
from .helpers import FrameView, KeyframeLoader, PreviewFrameLoader, ThumbnailLoader, TimeEdit
from .log_dialog import LogDialog
from .msgbox import ask_yes_no, show_about, show_info, show_warning
from .segment_panel import SegmentPanel
from .settings_dialog import SettingsDialog
from .timeline import Timeline
from .track_panel import TrackPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_settings = AppSettings()
        set_language(self.app_settings.language())
        output_dir = self.app_settings.output_dir()
        os.makedirs(output_dir, exist_ok=True)

        self.setWindowTitle(tr("CXVideoCutter - 无损视频剪辑"))
        self.setWindowIcon(app_icon())
        self.resize(1440, 920)
        self.setMinimumSize(1100, 700)

        # 数据
        self.sources: List[MediaSource] = []
        self.segments: List[Segment] = []
        self.chapters: List[Chapter] = []
        self.keyframes: List[float] = []
        self._keyframes_ready = False
        self.current_time = 0.0
        self.in_point = 0.0
        self.out_point = 0.0
        self._next_segment_id = 0
        self._key_loader: KeyframeLoader | None = None
        self._thumb_loader = ThumbnailLoader(self)
        self._thumb_loader.thumb_ready.connect(self._on_thumb_ready)
        self._worker: ExportWorker | None = None
        self._updating_slider = False
        self._step_labels: List[QLabel] = []
        self._preview_path = os.path.join(tempfile.gettempdir(), "cxvc_preview_frame.jpg")
        self._preview_time = -1.0
        self._preview_applied_id = 0
        self._video_page_ready = False
        self._taskbar = TaskbarProgress()

        # 帧预览条：当前帧居中，左右为前后帧
        self.filmstrip = FilmstripWidget(self)
        self.filmstrip.frameClicked.connect(self._on_filmstrip_clicked)
        self.filmstrip.countChanged.connect(lambda: self._request_filmstrip())
        self._filmstrip_loader = FilmstripLoader(self)
        self._filmstrip_loader.frames_ready.connect(self._on_filmstrip_frames)
        self._filmstrip_applied_id = 0
        # 合并拖拽进度条等密集定位请求，避免反复启动抽帧任务
        self._filmstrip_timer = QTimer(self)
        self._filmstrip_timer.setSingleShot(True)
        self._filmstrip_timer.setInterval(25)
        self._filmstrip_timer.timeout.connect(self._flush_filmstrip_request)
        self._pending_filmstrip_t = 0.0

        # 播放器
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.8)
        self.player.setAudioOutput(self.audio_output)
        self.video_widget = QVideoWidget(self)
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_player_position)
        self.player.playbackStateChanged.connect(self._on_playback_state)
        sink = self.player.videoSink()
        if sink is not None and hasattr(sink, "videoFrameChanged"):
            sink.videoFrameChanged.connect(self._on_video_frame)

        # 静帧预览（用 ffmpeg 按时间点抽帧，暂停/逐帧时显示，避免 QVideoWidget 停留在旧画面）
        self._preview_loader = PreviewFrameLoader(self)
        self._preview_loader.frame_ready.connect(self._on_preview_frame)

        self.export_panel = ExportPanel(self)
        self.export_panel.setOutputDir(output_dir)
        self._build_ui()
        self._wire()
        self._update_segment_ui()
        self._update_track_ui()
        self.statusBar().showMessage(f"FFmpeg: {probe_version()}")

    # ------------------------------------------------------------------
    # 静帧预览
    # ------------------------------------------------------------------
    def _show_frame_view(self) -> None:
        """切到静帧预览页（暂停、逐帧、打开视频后）。"""
        if self.preview_stack.currentIndex() != 0:
            self.preview_stack.setCurrentIndex(0)

    def _show_video_view(self) -> None:
        """切到实时播放页。"""
        if self.preview_stack.currentIndex() != 1:
            self.preview_stack.setCurrentIndex(1)

    def _request_preview_frame(self, t: float | None = None) -> None:
        """请求抽取当前时间点的静帧；t 为 None 时使用 current_time。"""
        if not self.sources:
            return
        if t is None:
            t = self.current_time
        t = max(0.0, float(t))
        self._preview_time = t
        self._show_frame_view()
        self._preview_loader.request(self.sources[0].path, t, self._preview_path)

    def _on_preview_frame(self, rid: int, path: str) -> None:
        if rid < self._preview_applied_id:
            return  # 丢弃过期结果，避免主画面被旧帧覆盖
        self._preview_applied_id = rid
        if self.frame_view.setPixmapPath(path):
            self._show_frame_view()

    def _on_video_frame(self, frame) -> None:
        """首个有效视频帧到达后再切换，避免播放初期黑屏。"""
        if frame is None or not getattr(frame, "isValid", lambda: True)():
            return
        if not self._video_page_ready:
            self._video_page_ready = True
            self._show_video_view()

    def _fallback_video_view(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._show_video_view()

    # ------------------------------------------------------------------
    # 帧预览条
    # ------------------------------------------------------------------
    def _request_filmstrip(self, t: float | None = None) -> None:
        """合并短时间内的多次请求；只在暂停/定位时调用，避免播放中频繁抽帧。"""
        if not self.sources:
            return
        self._pending_filmstrip_t = float(t if t is not None else self.current_time)
        self._filmstrip_timer.start(25)

    def _flush_filmstrip_request(self) -> None:
        if not self.sources:
            return
        self._filmstrip_loader.request(
            self.sources[0].path, self._pending_filmstrip_t, self._frame_interval(),
            self.sources[0].duration, self.filmstrip.count,
        )

    def _on_filmstrip_clicked(self, t: float) -> None:
        """点击帧预览：暂停并跳转到该帧，同时把它作为中心帧重新生成预览条。"""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        self.seek(t, force_filmstrip=True)
        # 立即用帧预览里已缓存的图片更新主画面，不必等 ffmpeg 重新抽帧
        cached = self.filmstrip.pixmap_for_time(t)
        if not cached.isNull():
            self.frame_view.setPixmap(cached)
            self._show_frame_view()

    def _on_filmstrip_frames(self, rid: int, frames: list) -> None:
        if rid < self._filmstrip_applied_id or len(frames) != self.filmstrip.count:
            return
        self._filmstrip_applied_id = rid
        self.filmstrip.set_frames(frames)

    # ------------------------------------------------------------------
    # 界面搭建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # 菜单
        self.menu_file = self.menuBar().addMenu(tr("文件(&F)"))
        self.act_open = QAction(tr("打开视频…"), self)
        self.act_open.setShortcut(QKeySequence("Ctrl+O"))
        self.act_open.triggered.connect(self.open_video)
        self.menu_file.addAction(self.act_open)
        self.act_audio = QAction(tr("添加外部音轨…"), self)
        self.act_audio.triggered.connect(lambda: self.add_external("audio"))
        self.menu_file.addAction(self.act_audio)
        self.act_sub = QAction(tr("添加外部字幕…"), self)
        self.act_sub.triggered.connect(lambda: self.add_external("subtitle"))
        self.menu_file.addAction(self.act_sub)
        self.menu_file.addSeparator()
        self.act_quit = QAction(tr("退出"), self)
        self.act_quit.triggered.connect(self.close)
        self.menu_file.addAction(self.act_quit)

        self.menu_edit = self.menuBar().addMenu(tr("编辑(&E)"))
        self.act_add_seg = QAction(tr("添加当前片段"), self)
        self.act_add_seg.triggered.connect(lambda: self.add_segment(self.in_point, self.out_point))
        self.menu_edit.addAction(self.act_add_seg)
        self.act_clear = QAction(tr("清空所有片段"), self)
        self.act_clear.triggered.connect(self.clear_segments)
        self.menu_edit.addAction(self.act_clear)

        self.menu_settings = self.menuBar().addMenu(tr("设置(&S)"))
        self.act_settings = QAction(tr("设置…"), self)
        self.act_settings.triggered.connect(self.open_settings)
        self.menu_settings.addAction(self.act_settings)

        self.menu_log = self.menuBar().addMenu(tr("日志(&L)"))
        self.act_logs = QAction(tr("查看日志…"), self)
        self.act_logs.triggered.connect(self.open_logs)
        self.menu_log.addAction(self.act_logs)

        self.menu_help = self.menuBar().addMenu(tr("帮助(&H)"))
        self.act_about = QAction(tr("关于"), self)
        self.act_about.triggered.connect(self._about)
        self.menu_help.addAction(self.act_about)

        # 工具栏（导出按钮位于右上角）
        toolbar = QToolBar(tr("主工具栏"))
        toolbar.setMovable(False)
        self.toolbar = toolbar
        self.addToolBar(toolbar)
        self.btn_open = QPushButton(tr("打开视频"))
        self.btn_open.clicked.connect(self.open_video)
        toolbar.addWidget(self.btn_open)
        self.file_label = QLabel(tr("未打开视频"))
        self.file_label.setProperty("muted", True)
        toolbar.addWidget(self.file_label)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.btn_export_top = QPushButton(tr("导出"))
        self.btn_export_top.setObjectName("primaryButton")
        self.btn_export_top.setFixedWidth(90)
        self.btn_export_top.clicked.connect(self.open_export_dialog)
        toolbar.addWidget(self.btn_export_top)

        # 左侧：预览 + 控制 + 时间轴
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(2)

        self.preview = QFrame()
        self.preview.setObjectName("preview")
        preview_layout = QVBoxLayout(self.preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_stack = QStackedWidget()
        self.frame_view = FrameView()
        self.preview_stack.addWidget(self.frame_view)     # 页 0：静帧
        self.preview_stack.addWidget(self.video_widget)   # 页 1：实时播放
        preview_layout.addWidget(self.preview_stack, 1)
        self.preview.setMinimumHeight(320)
        self.preview_stack.setCurrentIndex(0)
        # 左侧上下分割：视频预览高度可拖拽调整，右侧仍可调整宽度
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(self.preview)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(2)
        left_splitter.addWidget(controls)
        left_splitter.setSizes([560, 360])
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 0)
        left_splitter.setCollapsible(0, True)
        left_splitter.setCollapsible(1, False)
        left_layout.addWidget(left_splitter, 1)

        # 帧预览条（当前帧居中）
        controls_layout.addWidget(self.filmstrip)

        # 播放控制
        play_row = QHBoxLayout()
        self.btn_play = QPushButton(tr("▶ 播放"))
        self.btn_play.setFixedWidth(84)
        self.btn_stop = QPushButton(tr("■ 停止"))
        self.btn_stop.setFixedWidth(70)
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_label = QLabel("00:00:00.000 / 00:00:00.000")
        self.time_label.setMinimumWidth(230)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_mute = QPushButton(tr("静音"))
        self.btn_mute.setCheckable(True)
        self.btn_mute.setFixedWidth(48)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(84)
        self.volume_slider.setToolTip(tr("音量"))
        play_row.addWidget(self.btn_play)
        play_row.addWidget(self.btn_stop)
        play_row.addWidget(self.position_slider, 1)
        play_row.addWidget(self.btn_mute)
        play_row.addWidget(self.volume_slider)
        play_row.addWidget(self.time_label)
        controls_layout.addLayout(play_row)

        # 步进控制
        step_row = QHBoxLayout()
        step_row.setSpacing(0)
        self.label_seek = QLabel(tr("精确定位："))
        step_row.addWidget(self.label_seek)
        step_row.addSpacing(12)
        step_widget, label = self._make_step_widget(tr("逐帧:"), "frame")
        step_row.addWidget(step_widget)
        self._step_labels.append(label)
        step_row.addWidget(self._vseparator())
        step_widget, label = self._make_step_widget(tr("1 秒:"), "1s")
        step_row.addWidget(step_widget)
        self._step_labels.append(label)
        step_row.addWidget(self._vseparator())
        step_widget, label = self._make_step_widget(tr("30 秒:"), "30s")
        step_row.addWidget(step_widget)
        self._step_labels.append(label)
        step_row.addStretch(1)
        controls_layout.addLayout(step_row)

        # 入点 / 出点
        self.timeline = Timeline()
        io_row = QHBoxLayout()
        io_row.setSpacing(0)
        self.label_start = QLabel(tr("起点"))
        self.label_end = QLabel(tr("终点"))
        self.edit_in = TimeEdit()
        self.edit_out = TimeEdit()
        self.edit_in.timeChanged.connect(self._on_in_changed)
        self.edit_out.timeChanged.connect(self._on_out_changed)
        io_row.addWidget(self.label_start)
        io_row.addSpacing(8)
        io_row.addWidget(self.edit_in)
        io_row.addSpacing(12)
        self.btn_set_in = QPushButton(tr("设为起点 (I)"))
        self.btn_set_in.clicked.connect(self.set_in_point)
        io_row.addWidget(self.btn_set_in)
        # 起点组 / 终点组之间用与步进控件一致的分隔符
        io_row.addWidget(self._vseparator())
        io_row.addWidget(self.label_end)
        io_row.addSpacing(8)
        io_row.addWidget(self.edit_out)
        io_row.addSpacing(12)
        self.btn_set_out = QPushButton(tr("设为终点 (O)"))
        self.btn_set_out.clicked.connect(self.set_out_point)
        io_row.addWidget(self.btn_set_out)
        # 终点按钮与添加片段之间加大间隔，区分功能分组
        io_row.addSpacing(26)
        self.btn_add_seg = QPushButton(tr("+ 添加片段"))
        self.btn_add_seg.setObjectName("primaryButton")
        self.btn_add_seg.clicked.connect(lambda: self.add_segment(self.in_point, self.out_point))
        io_row.addWidget(self.btn_add_seg)
        io_row.addStretch(1)
        self.btn_zoom_out = QPushButton(tr("缩小 −"))
        self.btn_zoom_in = QPushButton(tr("放大 +"))
        self.btn_zoom_out.setFixedWidth(58)
        self.btn_zoom_in.setFixedWidth(58)
        self.btn_zoom_in.clicked.connect(self.timeline.zoomIn)
        self.btn_zoom_out.clicked.connect(self.timeline.zoomOut)
        io_row.addSpacing(16)
        io_row.addWidget(self.btn_zoom_out)
        io_row.addSpacing(6)
        io_row.addWidget(self.btn_zoom_in)
        controls_layout.addLayout(io_row)

        # 时间轴
        self.timeline.setToolTip(
            tr("时间轴（单击定位，拖拽至少 5 秒选择片段，Ctrl+滚轮缩放）")
        )
        self.timeline.seekRequested.connect(self.seek)
        self.timeline.segmentCreated.connect(self.add_segment)
        self.timeline.positionChanged.connect(
            lambda t: self.statusBar().showMessage(f"{tr('鼠标位置：')}{format_time(t)}", 2000)
        )
        controls_layout.addWidget(self.timeline, 0)

        # 右侧：片段 + 轨道
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 8, 8, 8)
        self.segment_panel = SegmentPanel()
        self.track_panel = TrackPanel()
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.segment_panel)
        splitter.addWidget(self.track_panel)
        splitter.setSizes([420, 380])
        right_layout.addWidget(splitter)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left)
        main_splitter.addWidget(right)
        main_splitter.setStretchFactor(0, 80)   # 右侧收窄，给左侧帧预览条更多宽度
        main_splitter.setStretchFactor(1, 20)
        main_splitter.setSizes([1152, 288])

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(main_splitter, 1)
        self.setCentralWidget(central)

        # 导出设置对话框
        self.export_dialog = ExportDialog(self.export_panel, self)

        # 快捷键
        self._act_play = QAction(tr("播放/暂停"), self)
        self._act_play.setShortcut(QKeySequence("Space"))
        self._act_play.triggered.connect(self.toggle_play)
        self.addAction(self._act_play)
        for key, slot in (
            ("Left", lambda: self.step(-1, "1s")),
            ("Right", lambda: self.step(1, "1s")),
            ("Ctrl+Left", lambda: self.step(-1, "frame")),
            ("Ctrl+Right", lambda: self.step(1, "frame")),
            ("I", self.set_in_point),
            ("O", self.set_out_point),
        ):
            act = QAction(self)
            act.setShortcut(QKeySequence(key))
            act.triggered.connect(slot)
            self.addAction(act)

    @staticmethod
    def _vseparator() -> QWidget:
        """竖向分隔符：自带左右等宽留白，保证前后间隔一致。"""
        wrapper = QWidget()
        wrapper.setFixedWidth(21)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(9, 0, 9, 0)
        layout.setSpacing(0)
        line = QWidget()
        line.setObjectName("vsep")
        line.setFixedSize(3, 22)
        layout.addWidget(line)
        return wrapper

    def _make_step_widget(self, label_text: str, mode: str):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        label = QLabel(label_text)
        layout.addWidget(label)
        prev = QPushButton("◀")
        nxt = QPushButton("▶")
        prev.setFixedWidth(30)
        nxt.setFixedWidth(30)
        prev.clicked.connect(lambda: self.step(-1, mode))
        nxt.clicked.connect(lambda: self.step(1, mode))
        layout.addWidget(prev)
        layout.addWidget(nxt)
        return widget, label

    def _wire(self) -> None:
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.position_slider.sliderMoved.connect(lambda v: self.seek(v / 1000.0))
        self.segment_panel.removeRequested.connect(self.remove_segment)
        self.segment_panel.locateRequested.connect(self._locate_segment)
        self.track_panel.addExternalRequested.connect(self.add_external)
        self.track_panel.removeTrackRequested.connect(self.remove_track)
        self.track_panel.addChapterRequested.connect(self.add_chapter)
        self.track_panel.removeChapterRequested.connect(self.remove_chapter)
        self.track_panel.chapterSelected.connect(self.seek)
        self.export_panel.exportRequested.connect(self.start_export)
        self.export_panel.cancelRequested.connect(self.cancel_export)

    # ------------------------------------------------------------------
    # 媒体打开与播放
    # ------------------------------------------------------------------
    def open_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("打开视频…"), "",
            f"{tr('视频文件 (*.mp4 *.mkv *.mov *.avi *.ts *.flv *.webm *.m4v)')};;"
            f"{tr('所有文件 (*.*)')}",
        )
        if not path:
            return
        log_info(f"打开视频: {path}")
        try:
            source = probe_media(path, 0)
            if not source.video_streams():
                raise RuntimeError(tr("文件中未找到可用轨道"))
        except Exception as exc:
            log_error(f"打开视频失败: {path} - {exc}")
            show_warning(self, tr("提示"), str(exc))
            return

        self.player.stop()
        self._video_page_ready = False
        self.sources = [source]
        self.segments = []
        self.chapters = []
        self.keyframes = []
        self._keyframes_ready = False
        self.current_time = 0.0
        self._next_segment_id = 0
        duration = source.duration
        self.in_point = 0.0
        self.out_point = min(duration, 10.0) if duration > 0 else 0.0

        self.file_label.setText(os.path.basename(path))
        self.player.setSource(QUrl.fromLocalFile(path))
        self.timeline.setMedia(duration, [])
        self.timeline.setInOut(self.in_point, self.out_point)
        self.position_slider.setRange(0, int(duration * 1000))
        self.edit_in.setSeconds(0)
        self.edit_out.setSeconds(self.out_point)
        self.frame_view.clear()
        self.filmstrip.clear()
        self.seek(0)   # 已包含静帧与帧预览条刷新
        self._update_segment_ui()
        self._update_track_ui()
        self.statusBar().showMessage(tr("正在扫描关键帧…"))

        if self._key_loader and self._key_loader.isRunning():
            self._key_loader.terminate()
        self._key_loader = KeyframeLoader(path, self)
        self._key_loader.finished_load.connect(self._on_keyframes)
        self._key_loader.start()

    def _on_keyframes(self, frames: List[float]) -> None:
        self.keyframes = frames
        self._keyframes_ready = True
        self.timeline.canvas.keyframes = frames
        self.timeline.canvas.update()
        self.statusBar().showMessage(f"{tr('关键帧已加载：')}{len(frames)}{tr('个')}")

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self) -> None:
        self.player.stop()
        self.seek(0)

    def seek(self, t: float, force_filmstrip: bool = False) -> None:
        if not self.sources:
            return
        self.current_time = max(0.0, min(float(t), self.sources[0].duration))
        if self.player.source() != QUrl():
            self.player.setPosition(int(self.current_time * 1000))
        self._updating_slider = True
        self.position_slider.setValue(int(self.current_time * 1000))
        self._updating_slider = False
        self.timeline.setPlayhead(self.current_time)
        self._update_time_label()
        # 暂停/停止时刷新静帧；播放时由 QVideoWidget 显示实时画面
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState or force_filmstrip:
            self._request_preview_frame()
            self._request_filmstrip()

    def _on_player_position(self, pos: int) -> None:
        self.current_time = pos / 1000.0
        if not self._updating_slider:
            self._updating_slider = True
            self.position_slider.setValue(pos)
            self._updating_slider = False
        self.timeline.setPlayhead(self.current_time)
        self._update_time_label()

    def _on_playback_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.btn_play.setText(tr("⏸ 暂停") if playing else tr("▶ 播放"))
        if playing:
            if self._video_page_ready:
                self._show_video_view()
            else:
                # 兜底：个别后端不触发 videoFrameChanged 时也能在短时间内切过去
                QTimer.singleShot(300, self._fallback_video_view)
        else:
            self._video_page_ready = False
            # 暂停/停止后用 ffmpeg 精确抽取当前帧，避免停留在旧画面
            self._request_preview_frame()
            self._request_filmstrip()

    def _on_volume_changed(self, value: int) -> None:
        self.audio_output.setVolume(max(0.0, min(1.0, value / 100.0)))
        if value > 0 and self.audio_output.muted():
            self.audio_output.setMuted(False)
            self.btn_mute.setChecked(False)
            self.btn_mute.setText(tr("静音"))

    def _toggle_mute(self, checked: bool) -> None:
        self.audio_output.setMuted(checked)
        self.btn_mute.setText(tr("取消静音") if checked else tr("静音"))

    def _update_time_label(self) -> None:
        total = self.sources[0].duration if self.sources else 0.0
        self.time_label.setText(f"{format_time(self.current_time)} / {format_time(total)}")

    # ------------------------------------------------------------------
    # 定位与选段
    # ------------------------------------------------------------------
    def _frame_interval(self) -> float:
        """按视频标称帧率返回一帧的时长（秒）。"""
        fps = 30.0
        if self.sources:
            streams = self.sources[0].video_streams()
            if streams:
                try:
                    fps = float(Fraction(streams[0].r_frame_rate or "30/1"))
                except (ValueError, ZeroDivisionError):
                    fps = 30.0
        if fps <= 0 or fps > 1000:
            fps = 30.0
        return 1.0 / fps

    def step(self, direction: int, mode: str) -> None:
        if not self.sources:
            return
        # 步进时先暂停，避免播放中的实时画面覆盖静帧预览
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        duration = self.sources[0].duration
        t = self.current_time
        if mode == "frame":
            # 对齐到整帧边界后再移动一帧，避免浮点累积导致画面不变化
            interval = self._frame_interval()
            t = round(t / interval) * interval + direction * interval
        elif mode == "1s":
            t += direction * 1.0
        elif mode == "30s":
            t += direction * 30.0
        t = max(0.0, min(duration, t))
        self.seek(t)   # seek 内部已请求静帧与帧预览条，避免重复抽帧

    def set_in_point(self) -> None:
        if not self.sources:
            return
        self.in_point = self.current_time
        if self.in_point >= self.out_point:
            self.out_point = min(self.sources[0].duration, self.in_point + 0.1)
        self.edit_in.setSeconds(self.in_point)
        self.edit_out.setSeconds(self.out_point)
        self.timeline.setInOut(self.in_point, self.out_point)

    def set_out_point(self) -> None:
        if not self.sources:
            return
        self.out_point = self.current_time
        if self.out_point <= self.in_point:
            self.in_point = max(0.0, self.out_point - 0.1)
        self.edit_in.setSeconds(self.in_point)
        self.edit_out.setSeconds(self.out_point)
        self.timeline.setInOut(self.in_point, self.out_point)

    def _on_in_changed(self, value: float) -> None:
        self.in_point = min(value, max(0.0, self.out_point - 0.01))
        self.edit_in.setSeconds(self.in_point)
        self.timeline.setInOut(self.in_point, self.out_point)

    def _on_out_changed(self, value: float) -> None:
        duration = self.sources[0].duration if self.sources else 0.0
        self.out_point = max(value, min(duration, self.in_point + 0.01))
        self.edit_out.setSeconds(self.out_point)
        self.timeline.setInOut(self.in_point, self.out_point)

    def add_segment(self, start: float, end: float) -> None:
        if not self.sources:
            show_info(self, tr("提示"), tr("请先打开视频文件"))
            return
        duration = self.sources[0].duration
        start = max(0.0, min(float(start), duration))
        end = max(0.0, min(float(end), duration))
        if end - start < 0.05:
            show_info(self, tr("提示"), tr("片段时长太短，请重新选择"))
            return
        if not self.app_settings.allow_segment_overlap():
            for existing in self.segments:
                # 完全重复或时间段交叠都视为冲突；首尾刚好相接不算重叠
                if start < existing.end - 1e-6 and existing.start < end - 1e-6:
                    show_info(
                        self, tr("提示"),
                        f"{tr('该时间段与已有片段重叠，请勿重复添加')}\n"
                        f"{format_time(existing.start)} → {format_time(existing.end)}",
                    )
                    return
        seg = Segment(start=start, end=end, id=self._next_segment_id)
        self._next_segment_id += 1
        self.segments.append(seg)
        self._update_segment_ui()
        self._thumb_loader.add(seg.id, self.sources[0].path, seg.start)
        self.statusBar().showMessage(
            f"{tr('已添加片段')} {len(self.segments)}：{format_time(start)} → {format_time(end)}"
        )

    def remove_segment(self, seg_id: int) -> None:
        self.segments = [s for s in self.segments if s.id != seg_id]
        self._update_segment_ui()

    def clear_segments(self) -> None:
        if not self.segments:
            return
        if ask_yes_no(self, tr("确定清空所有片段吗？")):
            self.segments = []
            self._update_segment_ui()

    def _locate_segment(self, seg_id: int) -> None:
        seg = next((s for s in self.segments if s.id == seg_id), None)
        if seg:
            self.seek(seg.start)

    def _on_thumb_ready(self, seg_id: int, path: str) -> None:
        seg = next((s for s in self.segments if s.id == seg_id), None)
        if seg:
            seg.thumbnail = path
        self.segment_panel.updateThumbnail(seg_id, path)

    def _update_segment_ui(self) -> None:
        self.segment_panel.setSegments(self.segments)
        self.timeline.setSegments(self.segments)

    # ------------------------------------------------------------------
    # 轨道与章节
    # ------------------------------------------------------------------
    def _update_track_ui(self) -> None:
        self.track_panel.setData(self.sources, self.chapters)

    def add_external(self, kind: str) -> None:
        if not self.sources:
            show_info(self, tr("提示"), tr("请先打开主视频"))
            return
        all_files = tr("所有文件 (*.*)")
        if kind == "audio":
            filt = f"{tr('音频文件 (*.mp3 *.aac *.m4a *.flac *.wav *.ogg *.opus *.wma)')};;{all_files}"
            wanted = "audio"
        else:
            filt = f"{tr('字幕文件 (*.srt *.ass *.ssa *.vtt)')};;{all_files}"
            wanted = "subtitle"
        path, _ = QFileDialog.getOpenFileName(
            self, tr("添加外部音轨…") if kind == "audio" else tr("添加外部字幕…"), "", filt
        )
        if not path:
            return
        try:
            source = probe_media(path, len(self.sources))
        except Exception as exc:
            show_warning(self, tr("添加失败"), str(exc))
            return
        source.streams = [s for s in source.streams if s.codec_type == wanted]
        if not source.streams:
            show_warning(self, tr("添加失败"), tr("文件中未找到可用轨道"))
            return
        for stream in source.streams:
            stream.external = True
        self.sources.append(source)
        self._update_track_ui()
        self.statusBar().showMessage(f"{tr('已添加外部轨道：')}{os.path.basename(path)}")

    def remove_track(self, input_index: int, stream_index: int) -> None:
        if input_index == 0:
            show_info(
                self, tr("提示"),
                tr("主视频文件自带的轨道不可移除，只能取消勾选（导出时不包含该轨道）。"),
            )
            return
        src = next((s for s in self.sources if s.input_index == input_index), None)
        if not src:
            return
        src.streams = [s for s in src.streams if s.index != stream_index]
        if not src.streams:
            self.sources.remove(src)
            for i, source in enumerate(self.sources):
                source.input_index = i
                for stream in source.streams:
                    stream.input_index = i
        self._update_track_ui()

    def _renumber_chapters(self) -> None:
        """按时间点顺序重新编号章节标题（增删后都调用）。"""
        self.chapters.sort(key=lambda c: c.time)
        for i, chapter in enumerate(self.chapters, start=1):
            chapter.title = tr("章节 {n}").format(n=i)

    def add_chapter(self) -> None:
        if not self.sources:
            show_info(self, tr("提示"), tr("请先打开视频文件"))
            return
        t = self.current_time
        # 同一时间点（毫秒级精度）只允许一个章节
        if any(abs(ch.time - t) < 0.001 for ch in self.chapters):
            show_info(self, tr("提示"), tr("该时间点已有章节，请勿重复添加"))
            return
        self.chapters.append(Chapter(t, ""))
        self._renumber_chapters()
        self._update_track_ui()

    def remove_chapter(self, row: int) -> None:
        if 0 <= row < len(self.chapters):
            self.chapters.pop(row)
            self._renumber_chapters()
            self._update_track_ui()

    # ------------------------------------------------------------------
    # 设置与导出
    # ------------------------------------------------------------------
    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self.app_settings.output_dir(), self.app_settings.language(),
            self.app_settings.theme(), self.app_settings.allow_segment_overlap(), self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            output_dir, language, theme, allow_overlap = dialog.values()
            if not output_dir:
                output_dir = default_output_dir()
            os.makedirs(output_dir, exist_ok=True)
            self.app_settings.set_output_dir(output_dir)
            self.app_settings.set_language(language)
            self.app_settings.set_theme(theme)
            self.app_settings.set_allow_segment_overlap(allow_overlap)
            set_language(language)
            apply_theme(QApplication.instance(), theme)
            self.export_panel.setOutputDir(output_dir)
            self.retranslate()
            self.timeline.canvas.update()
            self.statusBar().showMessage(tr("设置已保存"))

    def open_logs(self) -> None:
        cleanup_old_logs(30)
        dialog = LogDialog(self)
        dialog.exec()

    def open_export_dialog(self) -> None:
        self.export_panel._update_settings()
        self.export_dialog.show()
        self.export_dialog.raise_()
        self.export_dialog.activateWindow()

    def start_export(self) -> None:
        if not self.sources:
            show_info(self, tr("提示"), tr("请先打开视频文件"))
            return
        if not self.segments:
            show_info(self, tr("提示"), tr("请至少添加一个片段"))
            return

        self.export_panel._update_settings()
        settings = self.export_panel.settings
        if not settings.output_dir or not os.path.isdir(settings.output_dir):
            directory = QFileDialog.getExistingDirectory(
                self, tr("选择输出目录"), settings.output_dir or default_output_dir()
            )
            if not directory:
                return
            self.export_panel.setOutputDir(directory)
            settings = self.export_panel.settings

        self.export_panel.setBusy(True)
        self.export_panel.setProgress(0, tr("准备导出…"))
        self.export_dialog.setBusy(True)
        self._taskbar.set_hwnd(int(self.winId()))
        self._taskbar.set_state(self._taskbar.TBPF_NORMAL)
        self._taskbar.set_value(0)
        self._worker = ExportWorker(settings, list(self.sources), list(self.segments), list(self.chapters), self)
        self._worker.progress.connect(self._on_export_progress)
        self._worker.succeeded.connect(self._on_export_done)
        self._worker.failed.connect(self._on_export_failed)
        self._worker.cancelled.connect(self._on_export_cancelled)
        self._worker.start()

    def _on_export_progress(self, value: int, message: str) -> None:
        self.export_panel.setProgress(value, message)
        self._taskbar.set_value(value)

    def _on_export_done(self, outputs: List[str]) -> None:
        self._taskbar.set_value(100)
        self.export_panel.reset()
        self.export_dialog.setBusy(False)
        self._taskbar.reset()
        show_info(self, tr("完成"), tr("导出完成：") + "\n".join(outputs))

    def _on_export_failed(self, message: str) -> None:
        self._taskbar.set_state(self._taskbar.TBPF_ERROR)
        self.export_panel.reset()
        self.export_dialog.setBusy(False)
        self._taskbar.reset()
        show_warning(self, tr("导出失败"), message)

    def _on_export_cancelled(self, success: bool, reason: str) -> None:
        self.export_panel.reset()
        self.export_dialog.setBusy(False)
        self._taskbar.reset()
        if success:
            show_info(self, tr("取消成功"), tr("取消成功"))
        else:
            show_warning(self, tr("取消失败"), tr("取消失败") + "：" + reason)

    def cancel_export(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.export_panel.setProgress(0, tr("正在取消…"))

    # ------------------------------------------------------------------
    # 语言切换
    # ------------------------------------------------------------------
    def retranslate(self) -> None:
        self.setWindowTitle(tr("CXVideoCutter - 无损视频剪辑"))
        self.toolbar.setWindowTitle(tr("主工具栏"))
        self.menu_file.setTitle(tr("文件(&F)"))
        self.menu_edit.setTitle(tr("编辑(&E)"))
        self.menu_settings.setTitle(tr("设置(&S)"))
        self.menu_log.setTitle(tr("日志(&L)"))
        self.menu_help.setTitle(tr("帮助(&H)"))
        self.act_open.setText(tr("打开视频…"))
        self.act_audio.setText(tr("添加外部音轨…"))
        self.act_sub.setText(tr("添加外部字幕…"))
        self.act_quit.setText(tr("退出"))
        self.act_add_seg.setText(tr("添加当前片段"))
        self.act_clear.setText(tr("清空所有片段"))
        self.act_settings.setText(tr("设置…"))
        self.act_logs.setText(tr("查看日志…"))
        self.act_about.setText(tr("关于"))
        self.btn_open.setText(tr("打开视频"))
        self.btn_export_top.setText(tr("导出"))
        if not self.sources:
            self.file_label.setText(tr("未打开视频"))
        self.btn_play.setText(
            tr("⏸ 暂停") if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            else tr("▶ 播放")
        )
        self.btn_stop.setText(tr("■ 停止"))
        self.btn_mute.setText(tr("取消静音") if self.btn_mute.isChecked() else tr("静音"))
        self.volume_slider.setToolTip(tr("音量"))
        self.label_seek.setText(tr("精确定位："))
        for label, text in zip(self._step_labels, (tr("逐帧:"), tr("1 秒:"), tr("30 秒:"))):
            label.setText(text)
        self.label_start.setText(tr("起点"))
        self.label_end.setText(tr("终点"))
        self.btn_set_in.setText(tr("设为起点 (I)"))
        self.btn_set_out.setText(tr("设为终点 (O)"))
        self.btn_add_seg.setText(tr("+ 添加片段"))
        self.timeline.setToolTip(
            tr("时间轴（单击定位，拖拽至少 5 秒选择片段，Ctrl+滚轮缩放）")
        )
        self.btn_zoom_in.setText(tr("放大 +"))
        self.btn_zoom_out.setText(tr("缩小 −"))
        self._act_play.setText(tr("播放/暂停"))
        self.segment_panel.retranslate()
        self.track_panel.retranslate()
        self.export_panel.retranslate()
        self.export_dialog.retranslate()
        self.timeline.canvas.update()

    def _about(self) -> None:
        about_text = tr("关于文本")
        if about_text.startswith("CXVideoCutter"):
            about_text = about_text.replace(
                "CXVideoCutter", f"CXVideoCutter {APP_VERSION_TAG}", 1
            )
        else:
            about_text = f"CXVideoCutter {APP_VERSION_TAG}\n\n" + about_text
        show_about(self, tr("关于"), about_text + probe_version())

    def closeEvent(self, event) -> None:  # noqa: N802
        self._taskbar.reset()
        self.player.stop()
        self._thumb_loader.stop()
        self._preview_loader.stop()
        self._filmstrip_loader.stop()
        if self._key_loader and self._key_loader.isRunning():
            self._key_loader.terminate()
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        event.accept()
