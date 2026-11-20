# 第三方组件说明

本仓库随源码附带以下预编译二进制，仅供 CI 打包 CXVideoCutter 使用：

- `build_tools/ffmpeg-install/bin/ffmpeg.exe` / `ffprobe.exe`（Windows x64）
- `build_tools/arm64/ffmpeg-install/bin/ffmpeg.exe` / `ffprobe.exe`（Windows ARM64）

这些 FFmpeg 以 `--enable-gpl --enable-version3 --enable-libx264` 编译，因此遵循
GPLv3 及 libx264 的相应开源许可。将这些二进制随最终产品分发时，请确保：

1. 随产品提供对应源码获取方式或书面要约；
2. 保留 FFmpeg / x264 的版权与许可声明；
3. 遵守 GPLv3 的其他分发要求。

如需避免 GPL 义务，可改用 LGPL 构建的 FFmpeg（不带 libx264），或改为让用户自行安装 FFmpeg。
