# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for NTH — Windows one-file executable.
# Build:  pyinstaller build/NTH.spec --noconfirm  →  dist/NTH.exe

import os

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "data", "catalog.json"), "data"),
    (os.path.join(ROOT, "assets"), "assets"),
]
datas = [(src, dest) for src, dest in datas if os.path.exists(src)]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=["mss", "keyring.backends.Windows", "cv2", "PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "jupyter", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="NTH",
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
    icon=os.path.join(ROOT, "assets", "app_icon.ico")
    if os.path.exists(os.path.join(ROOT, "assets", "app_icon.ico")) else None,
)
