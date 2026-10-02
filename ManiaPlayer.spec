# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['mania_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('mania_harness.py', '.'), ('maniaplayer.py', '.')],
    hiddenimports=['mss', 'PIL', 'pynput', 'tkinter', 'json'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cv2'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ManiaPlayerGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
