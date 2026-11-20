"""Prepare ARM64 assets (PySide6, shiboken6, Python DLLs) for cross-freezing.

Run on x64 Windows with the x64 Python environment that also runs PyInstaller.
No ARM64 binary is executed here; wheels are only unpacked.
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARM = ROOT / "build_tools" / "arm64"
DOWN = ARM / "downloads"
PYSIDE = ARM / "pyside6"
PYDLL = ARM / "python"


def extract_zip(src: Path, dst: Path, only: set[str] | None = None) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if only is not None and name not in only:
                continue
            target = dst / name
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as fsrc, target.open("wb") as fdst:
                shutil.copyfileobj(fsrc, fdst)


def main() -> None:
    if PYSIDE.exists():
        shutil.rmtree(PYSIDE)
    if PYDLL.exists():
        shutil.rmtree(PYDLL)
    PYSIDE.mkdir(parents=True)
    PYDLL.mkdir(parents=True)

    for wheel in sorted(DOWN.glob("pyside6*win_arm64.whl")):
        print("unpack", wheel.name)
        extract_zip(wheel, PYSIDE)
    for wheel in sorted(DOWN.glob("shiboken6*win_arm64.whl")):
        print("unpack", wheel.name)
        extract_zip(wheel, PYSIDE)

    embed = DOWN / "python-3.13.14-embed-arm64.zip"
    with zipfile.ZipFile(embed) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".dll")]
    print("unpack", embed.name, len(names), "DLLs")
    extract_zip(embed, PYDLL, set(names))

    print("PySide6 root:", PYSIDE)
    print("Python DLLs:", PYDLL)


if __name__ == "__main__":
    main()
