"""数据模型：媒体源、轨道、片段、章节与导出设置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .i18n import tr


@dataclass
class StreamInfo:
    """一条轨道（视频 / 音频 / 字幕 / 附件）。"""

    index: int                       # 在该输入文件中的流索引
    input_index: int                 # ffmpeg 输入序号（主视频为 0）
    codec_type: str                  # video / audio / subtitle / attachment
    codec_name: str = ""
    width: int = 0
    height: int = 0
    r_frame_rate: str = ""
    channels: int = 0
    sample_rate: str = ""
    language: str = ""
    title: str = ""
    is_default: bool = False
    forced: bool = False
    enabled: bool = True             # 是否参与导出
    source_path: str = ""            # 所属文件路径
    external: bool = False           # 是否为后添加的外部轨道

    def label(self) -> str:
        parts = [f"[{self.input_index}:{self.index}]"]
        kind = {
            "video": tr("视频"),
            "audio": tr("音频"),
            "subtitle": tr("字幕"),
            "attachment": tr("附件"),
        }.get(self.codec_type, self.codec_type)
        parts.append(kind)
        if self.codec_name:
            parts.append(self.codec_name.upper())
        if self.codec_type == "video" and self.width and self.height:
            parts.append(f"{self.width}x{self.height}")
        if self.codec_type == "audio" and self.channels:
            parts.append(f"{self.channels}ch")
        if self.language:
            parts.append(self.language)
        if self.title:
            parts.append(self.title)
        if self.forced:
            parts.append(tr("强制"))
        return " ".join(parts)


@dataclass
class MediaSource:
    """一个输入文件（主视频或外部音轨/字幕）。"""

    path: str
    input_index: int
    duration: float = 0.0
    format_name: str = ""
    ext: str = ""
    streams: List[StreamInfo] = field(default_factory=list)

    def video_streams(self) -> List[StreamInfo]:
        return [s for s in self.streams if s.codec_type == "video"]

    def audio_streams(self) -> List[StreamInfo]:
        return [s for s in self.streams if s.codec_type == "audio"]

    def subtitle_streams(self) -> List[StreamInfo]:
        return [s for s in self.streams if s.codec_type == "subtitle"]


@dataclass
class Segment:
    """一个选中的视频片段。"""

    start: float
    end: float
    id: int = 0
    thumbnail: Optional[str] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Chapter:
    """一个章节标记。"""

    time: float
    title: str = ""


@dataclass
class ExportSettings:
    """导出设置。"""

    mode: str = "merge"              # merge=合并导出 / separate=多段分别导出
    resolution: str = "original"     # original / 720p / 1080p / 4k
    container: str = "original"      # original / mkv / mp4
    output_dir: str = ""

    RESOLUTION_HEIGHTS = {
        "original": 0,
        "720p": 720,
        "1080p": 1080,
        "4k": 2160,
    }
