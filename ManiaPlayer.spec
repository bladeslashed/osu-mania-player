# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['mania_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('mania_harness.py', '.'), ('maniaplayer.py', '.')],
    hiddenimports=['mss', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageGrab', 'pynput', 'pynput.keyboard', 'pynput.keyboard._win32', 'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.filedialog', 'json', 'collections'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cv2', 'numpy', 'scipy', 'matplotlib', 'pandas', 'unittest', 'test', 'email', 'http', 'html', 'urllib', 'xml', 'xmlrpc'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='maniaplayer',
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
