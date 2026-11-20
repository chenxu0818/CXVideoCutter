"""导出任务：无损剪辑、合并、剪辑并合并、轨道与章节处理。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from typing import Callable, List, Optional

from PySide6.QtCore import QThread, Signal

from .ffmpeg import FFMPEG, format_time
from .i18n import tr
from .logger import log_error, log_info
from .models import Chapter, ExportSettings, MediaSource, Segment, StreamInfo


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# _run_ffmpeg 用这两个标记向 ExportWorker 区分「取消成功 / 取消失败」
CANCEL_OK = "__CXVC_CANCEL_OK__"
CANCEL_FAIL_PREFIX = "__CXVC_CANCEL_FAIL__:"


def _kill_process_tree(proc: subprocess.Popen) -> tuple[bool, str]:
    """彻底结束 ffmpeg 进程树，返回 (是否成功, 失败原因)。

    ffmpeg 可能是 chocolatey shim 或带子进程启动器，单用 proc.terminate()
    只杀掉外层 shim，真正的 ffmpeg.exe 仍在后台吃 CPU。Windows 下用
    taskkill /T /F 连子进程一起结束。
    """
    if proc.poll() is not None:
        return True, ""
    kill_error = ""
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=NO_WINDOW, timeout=10,
            )
            if result.returncode != 0:
                kill_error = (result.stderr or result.stdout or b"").decode(
                    "utf-8", errors="replace"
                ).strip() or f"taskkill 退出码 {result.returncode}"
        else:
            proc.terminate()
    except (OSError, subprocess.SubprocessError) as exc:
        kill_error = str(exc)
    # 进程确实退出才算取消成功：taskkill 有时因竞态返回非 0，但进程已终止
    try:
        proc.wait(timeout=5)
        return True, ""
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
    except OSError as exc:
        kill_error = kill_error or str(exc)
    try:
        proc.wait(timeout=3)
        return True, ""
    except subprocess.TimeoutExpired:
        return False, kill_error or "ffmpeg 进程在强制结束后仍未退出"


def _run_ffmpeg(
    cmd: List[str],
    duration: float,
    progress_cb: Optional[Callable[[float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    context: str = "ffmpeg",
) -> tuple[bool, str]:
    """执行 ffmpeg，解析 -progress 输出，返回 (成功, 错误信息)。

    关键：stderr 必须在独立线程中实时排空。此前只在 stdout 读完后才读取
    stderr，当 ffmpeg 输出较多错误/警告时 stderr 管道缓冲区被写满，ffmpeg
    阻塞等待，stdout 也 No longer 输出，导致导出永久卡在 0%。
    """
    log_info(f"[{context}] 启动命令: {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
        )
    except OSError as exc:
        log_error(f"[{context}] 无法启动 ffmpeg: {exc}")
        return False, str(exc)

    # 独立线程实时收集 stderr，避免管道缓冲写满造成死锁
    stderr_lines: List[str] = []

    def _drain_stderr() -> None:
        try:
            assert proc.stderr is not None
            for raw in proc.stderr:
                line = raw.rstrip()
                if line:
                    stderr_lines.append(line)
                    log_info(f"[{context}] stderr: {line}")
        except Exception:
            pass

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    # 看门狗：独立于 stdout 轮询取消标志，一旦取消立刻杀掉整棵进程树。
    # 之前只在读到 stdout 行时才检查，ffmpeg 不输出进度时取消会迟迟不生效。
    cancelled = threading.Event()
    cancel_result: dict[str, str] = {}

    def _watch_cancel() -> None:
        while proc.poll() is None and not cancelled.is_set():
            if cancel_event is not None and cancel_event.wait(0.05):
                cancelled.set()
                ok, reason = _kill_process_tree(proc)
                cancel_result["ok"] = "1" if ok else "0"
                cancel_result["reason"] = reason
                return

    watcher = threading.Thread(target=_watch_cancel, daemon=True)
    if cancel_event is not None:
        watcher.start()

    last_frac = 0.0
    assert proc.stdout is not None
    for line in proc.stdout:
        if cancelled.is_set():
            break
        line = line.strip()
        if not line:
            continue
        frac = None
        if line.startswith("out_time_ms="):
            try:
                frac = int(line.split("=", 1)[1]) / 1_000_000.0 / max(duration, 0.001)
            except ValueError:
                frac = None
        elif line.startswith("out_time="):
            text = line.split("=", 1)[1]
            try:
                parts = text.split(":")
                secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                frac = secs / max(duration, 0.001)
            except (ValueError, IndexError):
                frac = None
        if frac is not None:
            frac = max(last_frac, min(1.0, frac))
            last_frac = frac
            if progress_cb:
                progress_cb(frac)

    cancelled.set()          # 结束看门狗
    code = proc.wait()
    stderr_thread.join(timeout=3)
    if cancel_event is not None and cancel_event.is_set():
        # taskkill 失败（例如权限不足）时，明确回报取消失败及原因
        if cancel_result.get("ok") == "0":
            reason = cancel_result.get("reason", "无法终止 ffmpeg 进程")
            log_error(f"[{context}] 取消失败: {reason}")
            return False, CANCEL_FAIL_PREFIX + reason
        log_info(f"[{context}] 用户取消成功")
        return False, CANCEL_OK
    if code != 0:
        tail = "\n".join(stderr_lines[-12:])
        log_error(f"[{context}] ffmpeg 失败，退出码 {code}: {tail}")
        return False, tail or f"ffmpeg 退出码 {code}"
    log_info(f"[{context}] 完成")
    if progress_cb:
        progress_cb(1.0)
    return True, ""


def _concat_line(path: str) -> str:
    p = path.replace("\\", "/").replace("'", "'\\''")
    return f"file '{p}'\n"


def remap_chapters(chapters: List[Chapter], segments: List[Segment]) -> List[Chapter]:
    """把原始时间轴上的章节映射到“合并后”的时间轴。"""
    result: List[Chapter] = []
    elapsed = 0.0
    for seg in segments:
        for ch in chapters:
            if seg.start <= ch.time < seg.end:
                result.append(Chapter(elapsed + (ch.time - seg.start), ch.title))
        elapsed += seg.duration
    result.sort(key=lambda c: c.time)
    return result


def write_ffmetadata(
    path: str,
    chapters: List[Chapter],
    offset: float = 0.0,
    limit: float = 0.0,
) -> bool:
    """生成章节元数据文件。时间均相对于 offset。"""
    valid = []
    for ch in chapters:
        rel = ch.time - offset
        if rel < 0 or (limit > 0 and rel >= limit - 0.001):
            continue
        valid.append((rel, ch.title))
    if not valid:
        return False

    lines = [";FFMETADATA1\n"]
    for i, (rel, title) in enumerate(valid):
        start_ms = int(round(rel * 1000))
        if i + 1 < len(valid):
            end_ms = int(round(valid[i + 1][0] * 1000))
        else:
            end_ms = int(round(limit * 1000)) if limit > 0 else start_ms + 1000
        if end_ms <= start_ms:
            end_ms = start_ms + 1000
        lines.append("[CHAPTER]\n")
        lines.append("TIMEBASE=1/1000\n")
        lines.append(f"START={start_ms}\n")
        lines.append(f"END={end_ms}\n")
        lines.append(f"title={title or tr('章节 {n}').format(n=i + 1)}\n")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except OSError:
        return False


class ExportWorker(QThread):
    """后台导出线程。"""

    progress = Signal(int, str)        # 百分比、状态文字
    succeeded = Signal(list)           # 输出文件路径列表
    failed = Signal(str)
    cancelled = Signal(bool, str)      # 是否取消成功、失败原因

    def __init__(
        self,
        settings: ExportSettings,
        sources: List[MediaSource],     # sources[0] 为主视频
        segments: List[Segment],
        chapters: List[Chapter],
        parent=None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.sources = sources
        self.segments = segments
        self.chapters = chapters
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def _emit(self, percent: int, message: str) -> None:
        self.progress.emit(max(0, min(100, int(percent))), message)

    def _handle_cancel_result(self, err: str) -> bool:
        """若 err 是取消标记，则发出 cancelled 信号并返回 True。"""
        if err == CANCEL_OK:
            self.cancelled.emit(True, "")
            return True
        if err.startswith(CANCEL_FAIL_PREFIX):
            self.cancelled.emit(False, err[len(CANCEL_FAIL_PREFIX):])
            return True
        return False

    # ------------------------------------------------------------------
    def run(self) -> None:
        temp_dir = ""
        log_info("=== 开始导出任务 ===")
        log_info(f"模式={self.settings.mode} 分辨率={self.settings.resolution} "
                 f"容器={self.settings.container} 输出目录={self.settings.output_dir} "
                 f"片段数={len(self.segments)} 章节数={len(self.chapters)}")
        try:
            if not self.sources:
                raise RuntimeError(tr("请先打开一个视频文件"))
            if not self.segments:
                raise RuntimeError(tr("请至少选择一个视频片段"))

            main = self.sources[0]
            ext = self._target_ext(main)
            height = ExportSettings.RESOLUTION_HEIGHTS.get(self.settings.resolution, 0)
            enabled = [s for src in self.sources for s in src.streams if s.enabled]
            if not enabled:
                raise RuntimeError(tr("请至少勾选一条需要导出的轨道"))
            log_info(f"主视频={main.path} 时长={main.duration:.3f}s 扩展名={ext} "
                     f"重编码高度={height} 启用轨道数={len(enabled)}")

            temp_dir = tempfile.mkdtemp(prefix="cxvc_")
            merge = self.settings.mode == "merge"
            total = len(self.segments) + (1 if merge else 0)
            outputs: List[str] = []
            concat_lines: List[str] = []

            stem = os.path.splitext(os.path.basename(main.path))[0]
            # 每次导出使用独立时间戳，避免重复导出时覆盖同名文件
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_info(f"导出时间戳={stamp}")

            for i, seg in enumerate(self.segments):
                if self.cancel_event.is_set():
                    self.cancelled.emit(True, "")
                    return
                if merge:
                    out_path = os.path.join(temp_dir, f"seg_{i + 1:05d}.{ext}")
                else:
                    out_path = os.path.join(
                        self.settings.output_dir, f"{stem}_{stamp}_片段{i + 1:02d}.{ext}"
                    )

                self._emit(
                    int(i * 100 / total),
                    tr("正在处理片段 {cur}/{total}  ({start} → {end})").format(
                        cur=i + 1, total=len(self.segments),
                        start=format_time(seg.start), end=format_time(seg.end),
                    ),
                )

                # 合并模式下章节只在最终文件写入，避免临时片段携带重复章节
                chapter_file = os.path.join(temp_dir, f"chapters_seg_{i + 1}.ffmeta")
                has_chapters = (not merge) and write_ffmetadata(
                    chapter_file, self.chapters, seg.start, seg.duration
                )

                cmd = self._build_segment_cmd(seg, out_path, ext, height, enabled,
                                              chapter_file if has_chapters else None)
                base = i * 100 / total
                span = 100 / total

                def cb(frac: float, b=base, s=span):
                    self._emit(
                        int(b + frac * s),
                        tr("正在处理片段 {cur}/{total}").format(
                            cur=i + 1, total=len(self.segments)
                        ),
                    )

                ok, err = _run_ffmpeg(cmd, seg.duration, cb, self.cancel_event,
                                      context=f"片段{i + 1}")
                if not ok:
                    if self._handle_cancel_result(err):
                        return
                    raise RuntimeError(tr("片段 {n} 剪辑失败：\n{err}").format(n=i + 1, err=err))
                outputs.append(out_path)
                concat_lines.append(_concat_line(out_path))

            if merge:
                if self.cancel_event.is_set():
                    self.cancelled.emit(True, "")
                    return
                merged_path = os.path.join(self.settings.output_dir, f"{stem}_{stamp}_合并.{ext}")
                self._emit(int((total - 1) * 100 / total), tr("正在合并片段…"))

                list_path = os.path.join(temp_dir, "concat.txt")
                with open(list_path, "w", encoding="utf-8") as f:
                    f.writelines(concat_lines)

                cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-progress", "pipe:1"]
                cmd += ["-f", "concat", "-safe", "0", "-i", list_path]

                chapter_file = os.path.join(temp_dir, "chapters_merge.ffmeta")
                total_duration = sum(s.duration for s in self.segments)
                mapped = remap_chapters(self.chapters, self.segments)
                has_chapters = write_ffmetadata(chapter_file, mapped, 0.0, total_duration)
                if has_chapters:
                    cmd += ["-i", chapter_file]  # concat 输入为 0，元数据输入为 1

                # 所有输入之后才是输出选项
                cmd += ["-map", "0", "-c", "copy"]
                if has_chapters:
                    cmd += ["-map_metadata", "1", "-map_chapters", "1"]
                if ext == "mp4":
                    cmd += ["-movflags", "+faststart"]
                cmd.append(merged_path)

                ok, err = _run_ffmpeg(cmd, total_duration,
                                      lambda frac: self._emit(
                                          int((total - 1 + frac) * 100 / total),
                                          tr("正在合并片段…"),
                                      ),
                                      self.cancel_event, context="合并")
                if not ok:
                    if self._handle_cancel_result(err):
                        return
                    raise RuntimeError(tr("合并失败：\n{err}").format(err=err))
                outputs = [merged_path]

            self._emit(100, tr("导出完成"))
            log_info(f"=== 导出成功，输出 {len(outputs)} 个文件: {outputs} ===")
            self.succeeded.emit(outputs)

        except RuntimeError as exc:
            log_error(f"=== 导出失败: {exc} ===")
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            log_error(f"=== 导出异常: {exc} ===")
            self.failed.emit(tr("导出出错：{err}").format(err=exc))
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    def _target_ext(self, main: MediaSource) -> str:
        if self.settings.container == "mkv":
            return "mkv"
        if self.settings.container == "mp4":
            return "mp4"
        return main.ext or "mp4"

    def _build_segment_cmd(
        self,
        seg: Segment,
        out_path: str,
        ext: str,
        height: int,
        enabled: List[StreamInfo],
        chapter_file: Optional[str],
    ) -> List[str]:
        cmd = [
            FFMPEG, "-hide_banner", "-nostdin", "-y",
            "-loglevel", "error", "-progress", "pipe:1",
        ]
        duration = f"{seg.duration:.6f}"
        start = f"{max(0.0, seg.start):.6f}"
        for src in self.sources:
            cmd += ["-ss", start, "-t", duration, "-i", src.path]

        chapter_input = len(self.sources)
        if chapter_file:
            cmd += ["-i", chapter_file]

        # 所有输入添加完毕后再写输出选项
        for s in enabled:
            cmd += ["-map", f"{s.input_index}:{s.index}"]

        if height > 0:
            cmd += [
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-vf", f"scale=-2:{height}",
            ]
        else:
            cmd += ["-c:v", "copy"]

        cmd += ["-c:a", "copy"]
        if ext == "mp4":
            cmd += ["-c:s", "mov_text"]
        else:
            cmd += ["-c:s", "copy"]

        cmd += ["-avoid_negative_ts", "make_zero"]
        if chapter_file:
            cmd += ["-map_metadata", str(chapter_input),
                    "-map_chapters", str(chapter_input)]
        if ext == "mp4":
            cmd += ["-movflags", "+faststart"]
        cmd.append(out_path)
        return cmd
