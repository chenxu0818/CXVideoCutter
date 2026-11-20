#!/usr/bin/env bash
# 在 Apple Silicon (arm64) Mac 上构建 CXVideoCutter.app
# 用法：在 macOS 终端执行  bash build_macos_app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
echo "项目目录: $ROOT"

# 必须在 Apple Silicon 上构建（PyInstaller 不是交叉编译器）
ARCH="$(uname -m)"
if [ "$ARCH" != "arm64" ]; then
  echo "错误：本脚本仅支持 Apple Silicon (arm64)，当前架构 $ARCH。" >&2
  echo "如需在 Intel Mac 构建，请改用 universal2 wheel 并去掉架构检查。" >&2
  exit 1
fi

# 源码使用了 Python 3.10+ 的 PEP 604 类型标注（X | None）
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "未找到 Python 3.10+，尝试通过 Homebrew 安装 python@3.12 ..." >&2
  if command -v brew >/dev/null 2>&1; then
    brew install python@3.12 >/dev/null
    PY="$(brew --prefix python@3.12)/bin/python3.12"
  else
    echo "错误：请安装 Python 3.10+ 或 Homebrew 后重试。" >&2
    exit 1
  fi
fi
echo "Python: $($PY --version 2>&1)"

# 使用独立虚拟环境，规避 macOS 的 PEP 668 externally-managed-environment 限制
VENV="$ROOT/build_tools/macos/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  $PY -m venv "$VENV"
fi
PY="$VENV/bin/python"
echo "Virtual env Python: $($PY --version 2>&1)"

# 1) 依赖：PySide6 在 macOS 提供 universal2 wheel（含 arm64）
$PY -m pip install --upgrade pip
$PY -m pip install "PySide6>=6.7,<7" "pyinstaller>=6.5,<7"

# 2) 下载 Apple Silicon 版静态 ffmpeg / ffprobe（约 28MB 各）
FF_DIR="$ROOT/build_tools/macos/ffmpeg"
mkdir -p "$FF_DIR"
if [ ! -x "$FF_DIR/ffmpeg" ]; then
  echo "下载 ffmpeg (Apple Silicon) ..."
  curl -L --fail --retry 3 -o "$FF_DIR/ffmpeg902arm.zip" \
    "https://www.osxexperts.net/ffmpeg902arm.zip"
  unzip -o "$FF_DIR/ffmpeg902arm.zip" -d "$FF_DIR"
fi
if [ ! -x "$FF_DIR/ffprobe" ]; then
  echo "下载 ffprobe (Apple Silicon) ..."
  curl -L --fail --retry 3 -o "$FF_DIR/ffprobe902arm.zip" \
    "https://www.osxexperts.net/ffprobe902arm.zip"
  unzip -o "$FF_DIR/ffprobe902arm.zip" -d "$FF_DIR"
fi
# 解压后的文件名可能是 ffmpeg / ffmpeg-arm64 等，统一改名并赋予执行权限
for pair in "ffmpeg" "ffprobe"; do
  found="$(find "$FF_DIR" -maxdepth 1 -type f -iname "${pair}*" -perm -u+x | head -1 || true)"
  if [ -n "$found" ] && [ "$found" != "$FF_DIR/$pair" ]; then
    mv -f "$found" "$FF_DIR/$pair"
  fi
  chmod +x "$FF_DIR/$pair"
done
# 去掉隔离属性并 ad-hoc 签名，避免 macOS Gatekeeper 拦截
xattr -dr com.apple.quarantine "$FF_DIR" 2>/dev/null || true
codesign -s - --force "$FF_DIR/ffmpeg" 2>/dev/null || true
codesign -s - --force "$FF_DIR/ffprobe" 2>/dev/null || true
file "$FF_DIR/ffmpeg" "$FF_DIR/ffprobe"

# 3) macOS 应用图标：把 ICO 转成 ICNS（若可用）
#    使用字符串变量以兼容 macOS 自带的 bash 3.2（空数组在 set -u 下会报错）
ICON_PATH=""
if command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1; then
  ICONSET="$ROOT/build_tools/macos/cxvc.iconset"
  rm -rf "$ICONSET"; mkdir -p "$ICONSET"
  for sz in 16 32 64 128 256 512; do
    sips -z $sz $sz "$ROOT/app/resources/icon.ico" --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null 2>&1 || true
    sips -z $((sz*2)) $((sz*2)) "$ROOT/app/resources/icon.ico" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null 2>&1 || true
  done
  if iconutil -c icns "$ICONSET" -o "$ROOT/build_tools/macos/cxvc.icns"; then
    ICON_PATH="$ROOT/build_tools/macos/cxvc.icns"
  fi
fi

# 4) PyInstaller 打包为 .app bundle
OUT="$ROOT/dist"
mkdir -p "$OUT"
PYI_ARGS=(
  --noconfirm --clean --windowed
  --name CXVideoCutter
)
if [ -n "$ICON_PATH" ]; then
  PYI_ARGS+=(--icon "$ICON_PATH")
fi
$PY -m PyInstaller "${PYI_ARGS[@]}" \
  --add-data "$ROOT/app/resources/icon.ico:app/resources" \
  --add-data "$FF_DIR/ffmpeg:ffmpeg" \
  --add-data "$FF_DIR/ffprobe:ffmpeg" \
  --exclude-module tkinter --exclude-module numpy --exclude-module torch \
  --exclude-module gradio --exclude-module matplotlib --exclude-module PIL \
  --distpath "$OUT" \
  --workpath "$ROOT/build_tools/macos/build" \
  --specpath "$ROOT/build_tools/macos" \
  "$ROOT/main.py"

APP="$OUT/CXVideoCutter.app"
# ad-hoc 签名整个 app（本机运行无需开发者证书；分发给他人需 notarization）
codesign -s - --force --deep "$APP" 2>/dev/null || true
echo "完成：$APP"
echo "可将该 .app 压缩分发：cd \"$OUT\" && zip -ry CXVideoCutter-macos-arm64.zip CXVideoCutter.app"
