#!/usr/bin/env python3
"""从 app/resources/icon.ico 直接提取 PNG 帧，构建 macOS .icns。

ICO 内嵌的每一帧本身就是 PNG，不需要 sips 从 ICO 转换（sips 在不同
macOS 版本上对 ICO 输入支持不一致，且失败会被 shell 的 ``|| true``
吞掉，最终生成残缺 iconset，PyInstaller 只能使用默认图标）。

只依赖 Python 标准库 + macOS 自带的 sips / iconutil。
"""
from __future__ import annotations

import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ICO = ROOT / "app" / "resources" / "icon.ico"
ICONSET = ROOT / "build_tools" / "macos" / "cxvc.iconset"
ICNS = ROOT / "build_tools" / "macos" / "cxvc.icns"

# iconset 文件名 -> ICO 帧尺寸；这些尺寸 ICO 里都有原生 PNG，直接复制。
EXACT = {
    "icon_16x16.png": (16, 16),
    "icon_16x16@2x.png": (32, 32),
    "icon_32x32.png": (32, 32),
    "icon_32x32@2x.png": (64, 64),
    "icon_128x128.png": (128, 128),
    "icon_128x128@2x.png": (256, 256),
    "icon_256x256.png": (256, 256),
}

# 大尺寸 ICO 里没有，用 256 PNG 经 sips 放大（PNG 输入是可靠的）。
UPSCALE = {
    "icon_256x256@2x.png": 512,
    "icon_512x512.png": 512,
    "icon_512x512@2x.png": 1024,
}


def extract_png_frames(path: Path) -> dict[tuple[int, int], bytes]:
    data = path.read_bytes()
    if data[:4] not in (b"\x00\x00\x01\x00",):
        raise SystemExit(f"not an ICO file: {path}")
    count = struct.unpack_from("<H", data, 4)[0]
    frames: dict[tuple[int, int], bytes] = {}
    for index in range(count):
        header = 6 + 16 * index
        width, height, _, _, _, _, size, offset = struct.unpack_from(
            "<BBBBHHII", data, header
        )
        width, height = width or 256, height or 256
        blob = data[offset:offset + size]
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            frames[(width, height)] = blob
    return frames


def main() -> None:
    if not ICO.is_file():
        raise SystemExit(f"missing icon source: {ICO}")

    frames = extract_png_frames(ICO)
    print(f"extracted {len(frames)} PNG frames from {ICO}")

    ICONSET.mkdir(parents=True, exist_ok=True)
    for old in ICONSET.glob("*.png"):
        old.unlink()

    for name, key in EXACT.items():
        blob = frames.get(key)
        if blob is None:
            raise SystemExit(f"ICO has no {key[0]}x{key[1]} PNG frame")
        (ICONSET / name).write_bytes(blob)

    source_256 = ICONSET / "icon_256x256.png"
    for name, pixels in UPSCALE.items():
        target = ICONSET / name
        subprocess.run(
            ["sips", "-z", str(pixels), str(pixels), str(source_256),
             "--out", str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
        )

    if ICNS.exists():
        ICNS.unlink()
    subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS)], check=True
    )
    if not ICNS.is_file() or ICNS.stat().st_size < 1024:
        raise SystemExit("iconutil did not produce a valid icns")
    print(f"icns: {ICNS} ({ICNS.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
