# -*- mode: python ; coding: utf-8 -*-
"""Windows x64 one-file build with unused Qt payload removed."""
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
ICON = os.path.join(ROOT, "app", "resources", "icon.ico")
FFMPEG = os.path.join(ROOT, "build_tools", "ffmpeg-install", "bin", "ffmpeg.exe")
FFPROBE = os.path.join(ROOT, "build_tools", "ffmpeg-install", "bin", "ffprobe.exe")
VERSION_INFO = os.path.join(ROOT, "build_tools", "windows", "version_info.txt")

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (ICON, "app/resources"),
        (FFMPEG, "ffmpeg"),
        (FFPROBE, "ffmpeg"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "numpy", "torch", "gradio", "matplotlib", "PIL",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSvg",
        "PySide6.QtSvgWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel", "PySide6.QtBluetooth", "PySide6.QtNfc",
        "PySide6.QtPositioning", "PySide6.QtSerialPort", "PySide6.QtSql",
        "PySide6.QtTest", "PySide6.QtTextToSpeech", "PySide6.QtVirtualKeyboard",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtConcurrent",
    ],
    noarchive=False,
    optimize=0,
)

DROP_BINARIES = {
    "opengl32sw.dll",
    "qt6qml.dll", "qt6qmlmodels.dll", "qt6qmlworkerscript.dll",
    "qt6quick.dll", "qt6quick3d.dll", "qt6quickwidgets.dll",
    "qt6pdf.dll", "qt6pdfwidgets.dll",
    "qt6svg.dll", "qt6svgwidgets.dll",
    "qt6charts.dll", "qt6chartswidgets.dll",
    "qt6datavisualization.dll", "qt6datavisualizationwidgets.dll",
    "qt6webenginecore.dll", "qt6webenginewidgets.dll", "qt6webchannel.dll",
    "qt6bluetooth.dll", "qt6nfc.dll", "qt6positioning.dll",
    "qt6serialport.dll", "qt6sql.dll", "qt6test.dll",
    "qt6texttospeech.dll", "qt6virtualkeyboard.dll",
    "qt6designer.dll", "qt6help.dll", "qt6concurrent.dll",
}

a.binaries = [
    item for item in a.binaries
    if os.path.basename(item[0]).lower() not in DROP_BINARIES
]
a.datas = [
    item for item in a.datas
    if not item[0].lower().endswith(".qm")
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CXVideoCutter-v1.0.1-win-x64",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON],
    version=VERSION_INFO,
)
