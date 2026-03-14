# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['desktop_buddy.py'],
    pathex=[],
    binaries=[],
    datas=[('menu.css', '.'), ('Characters', 'Characters')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DesktopBuddy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DesktopBuddy',
)
app = BUNDLE(
    coll,
    name='DesktopBuddy.app',
    icon=None,
    bundle_identifier=None,
)
