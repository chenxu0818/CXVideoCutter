"""FFmpeg / FFprobe 命令行封装。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

from .i18n import tr
from .models import MediaSource, StreamInfo


# 不弹出控制台窗口（Windows）
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


# ---------------------------------------------------------------------------
# 工具定位
# ---------------------------------------------------------------------------

def _candidate_dirs() -> List[str]:
    dirs = []
    # 打包后随程序附带的 ffmpeg（可选）
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    dirs.append(os.path.join(base, "ffmpeg"))
    dirs.append(os.path.join(base, "bin"))
    # 打包后 EXE 所在目录（方便把 ffmpeg.exe / ffprobe.exe 放在旁边）
    dirs.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "ffmpeg"))
    dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    # 常见安装位置
    dirs.extend([
        r"C:\ffmpeg\bin",
        r"C:\ProgramData\chocolatey\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\tools\ffmpeg\bin",
        r"C:\chenxu\tools\ffmpeg-5.1-full_build\bin",
    ])
    return [d for d in dirs if d and os.path.isdir(d)]


def find_tool(name: str) -> str:
    """查找 ffmpeg / ffprobe；打包版优先使用随 EXE 附带的精简二进制。"""
    exe = name + (".exe" if os.name == "nt" else "")
    dirs = _candidate_dirs()
    if getattr(sys, "frozen", False):
        # 打包后前四个目录是 _MEIPASS 与 EXE 同目录，优先于系统 PATH
        for d in dirs[:4]:
            p = os.path.join(d, exe)
            if os.path.isfile(p):
                return p
    found = shutil.which(name)
    if found:
        return found
    for d in dirs:
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    return name  # 交给系统报错，提示更直观


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


# ---------------------------------------------------------------------------
# 时间格式化
# ---------------------------------------------------------------------------

def format_time(seconds: float, milliseconds: bool = True) -> str:
    """秒 -> HH:MM:SS.mmm（或 HH:MM:SS）。"""
    if seconds is None or seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    if milliseconds:
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_time(text: str) -> float:
    """HH:MM:SS.mmm / MM:SS.mmm / 秒数 -> 秒。"""
    text = (text or "").strip().replace(",", ".")
    if not text:
        return 0.0
    try:
        parts = text.split(":")
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return 0.0
    return 0.0


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# ffprobe
# ---------------------------------------------------------------------------

def probe_media(path: str, input_index: int = 0) -> MediaSource:
    """探测文件信息，返回 MediaSource。失败时抛出异常。"""
    cmd = [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", path]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=NO_WINDOW)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"无法读取媒体信息：{proc.stderr.strip() or path}")
    data = json.loads(proc.stdout)

    fmt = data.get("format", {}) or {}
    duration = _float(fmt.get("duration"))
    streams: List[StreamInfo] = []
    for st in data.get("streams", []) or []:
        tags = st.get("tags", {}) or {}
        disp = st.get("disposition", {}) or {}
        streams.append(StreamInfo(
            index=_int(st.get("index")),
            input_index=input_index,
            codec_type=st.get("codec_type", ""),
            codec_name=st.get("codec_name", ""),
            width=_int(st.get("width")),
            height=_int(st.get("height")),
            r_frame_rate=st.get("r_frame_rate", ""),
            channels=_int(st.get("channels")),
            sample_rate=str(st.get("sample_rate", "") or ""),
            language=str(tags.get("language", "") or ""),
            title=str(tags.get("title", "") or ""),
            is_default=bool(disp.get("default")),
            forced=bool(disp.get("forced")),
            source_path=path,
        ))
        if duration <= 0:
            duration = _float(st.get("duration"))

    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return MediaSource(
        path=path,
        input_index=input_index,
        duration=duration,
        format_name=fmt.get("format_name", ""),
        ext=ext,
        streams=streams,
    )


def _probe_keyframes_from_packets(path: str) -> List[float]:
    """方式一：通过 packet flags 读取关键帧（最快）。"""
    cmd = [
        FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "packet=pts_time,flags",
        "-of", "csv=p=0", path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=180, creationflags=NO_WINDOW)
    except (subprocess.TimeoutExpired, OSError):
        return []
    times: List[float] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        # 某些版本会输出 side_data 等额外字段，flags 可能不在第二列
        flags = next((p.strip() for p in parts[1:] if "K" in p and len(p.strip()) <= 8), "")
        if "K" in flags:
            t = _float(parts[0], -1)
            if t >= 0:
                times.append(t)
    return times


def _probe_keyframes_from_frames(path: str) -> List[float]:
    """方式二：只解码关键帧，兼容 packet 中无 flags 的容器。"""
    cmd = [
        FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-skip_frame", "nokey",
        "-show_entries", "frame=best_effort_timestamp_time,pts_time,pkt_dts_time",
        "-of", "csv=p=0", path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=300, creationflags=NO_WINDOW)
    except (subprocess.TimeoutExpired, OSError):
        return []
    times: List[float] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # 各 ffprobe 版本列顺序不同，取第一个合法时间
        for field in line.split(","):
            t = _float(field.strip(), -1)
            if t >= 0:
                times.append(t)
                break
    return times


def get_keyframes(path: str) -> List[float]:
    """读取视频流关键帧时间点（升序），带多种探测方式兜底。"""
    times = _probe_keyframes_from_packets(path)
    if not times:
        times = _probe_keyframes_from_frames(path)
    times = sorted(set(round(t, 6) for t in times if t >= 0))
    # 首帧通常为关键帧；若探测结果缺失则补上，保证能定位到开头
    if times and times[0] > 0.02:
        times.insert(0, 0.0)
    return times


def extract_frame(path: str, time: float, output_path: str, width: int = 320) -> bool:
    """抽取指定时间点的画面缩略图。"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    cmd = [
        FFMPEG, "-v", "error", "-y",
        "-ss", f"{max(0.0, time):.3f}", "-i", path,
        "-frames:v", "1",
    ]
    if width > 0:
        cmd += ["-vf", f"scale={width}:-2"]
    cmd += ["-q:v", "4", output_path]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=60, creationflags=NO_WINDOW)
        return proc.returncode == 0 and os.path.isfile(output_path)
    except (subprocess.TimeoutExpired, OSError):
        return False


def extract_frame_window(
    path: str,
    start: float,
    count: int,
    out_dir: str,
    prefix: str = "win",
    width: int = 240,
) -> List[str]:
    """用一个 ffmpeg 进程连续抽取 count 帧，返回按时间排序的图片路径。

    相比逐帧调用 extract_frame，省去 N-1 次进程启动，帧预览刷新从约 1 秒
    降到 0.1 秒左右。start 使用 6 位小数，保证与逐帧定位同一帧。
    """
    count = max(1, int(count))
    os.makedirs(out_dir, exist_ok=True)
    pattern = os.path.join(out_dir, f"{prefix}_%04d.jpg")
    cmd = [
        FFMPEG, "-v", "error", "-y",
        "-ss", f"{max(0.0, start):.6f}", "-i", path,
        "-fps_mode", "vfr", "-frames:v", str(count),
    ]
    if width > 0:
        cmd += ["-vf", f"scale={width}:-2"]
    cmd += ["-q:v", "4", pattern]

    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, creationflags=NO_WINDOW,
        )

    try:
        proc = _run()
        if proc.returncode != 0 and "fps_mode" in (proc.stderr or ""):
            # 兼容旧版 ffmpeg：去掉 fps_mode 再试一次
            i = cmd.index("-fps_mode")
            del cmd[i:i + 2]
            proc = _run()
        if proc.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, OSError):
        return []

    return sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir)
        if f.startswith(f"{prefix}_") and f.endswith(".jpg")
    )[:count]


def probe_version() -> str:
    try:
        proc = subprocess.run([FFMPEG, "-version"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=10,
                              creationflags=NO_WINDOW)
        return proc.stdout.splitlines()[0] if proc.stdout else tr("未知")
    except Exception:
        return tr("未知")
