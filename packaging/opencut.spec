# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for OpenCut PySide - Windows only.

Build:
    pwsh scripts/build_windows.ps1

Output:
    dist/OpenCut/OpenCut.exe (one-folder bundle)

Pre-requisite: download ffmpeg.exe and place it at packaging/bin/ffmpeg.exe.
"""

from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - provided by PyInstaller
FFMPEG_BIN = PROJECT_ROOT / "packaging" / "bin" / "ffmpeg.exe"

binaries = []
if FFMPEG_BIN.exists():
    binaries.append((str(FFMPEG_BIN), "bin"))
else:
    raise SystemExit(
        "Missing packaging/bin/ffmpeg.exe - download from "
        "https://www.gyan.dev/ffmpeg/builds/ then place at packaging/bin/ffmpeg.exe"
    )

datas = [
    (str(PROJECT_ROOT / "ui" / "resources"), "ui/resources"),
    (str(PROJECT_ROOT / "i18n"), "i18n"),
]

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy",
        "scipy",
        "matplotlib",
        "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpenCut",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "packaging" / "icon.ico")
    if (PROJECT_ROOT / "packaging" / "icon.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OpenCut",
)
