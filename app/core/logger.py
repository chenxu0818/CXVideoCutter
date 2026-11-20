"""按天分割的应用日志：log/YYYY-MM-DD.log。

用于记录导出命令、ffmpeg 输出、错误等，便于离线分析问题。
日志写入失败不会影响程序主流程。
"""

from __future__ import annotations

import datetime
import os
import threading
from typing import Optional

from .settings import app_root

_LOCK = threading.Lock()
_DIR: Optional[str] = None


def log_dir() -> str:
    """日志目录：软件根目录下的 log。"""
    global _DIR
    if _DIR is None:
        _DIR = os.path.join(app_root(), "log")
    return _DIR


def current_log_path() -> str:
    return os.path.join(log_dir(), datetime.date.today().isoformat() + ".log")


def log(message: str, level: str = "INFO") -> None:
    """追加一行日志。level: INFO / WARN / ERROR。"""
    try:
        directory = log_dir()
        os.makedirs(directory, exist_ok=True)
        line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} [{level}] {message}\n"
        with _LOCK:
            with open(current_log_path(), "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass  # 日志失败不应影响功能


def log_info(message: str) -> None:
    log(message, "INFO")


def log_warn(message: str) -> None:
    log(message, "WARN")


def log_error(message: str) -> None:
    log(message, "ERROR")
