# BlockAdventure.spec - PyInstaller build recipe.
#
#   pyinstaller BlockAdventure.spec --noconfirm
#
# Run it on the OS you want to ship for: PyInstaller does NOT cross-compile, so
# a Windows .exe must be produced on Windows (or under Wine). See build.py.
#
# There are no data files to bundle. Every sprite and every sound in this game is
# generated at runtime, so the whole build is code plus the pygame runtime.

import os

block_cipher = None

ICON = os.path.join("build", "icon.ico")
if not os.path.exists(ICON):
    ICON = None                      # build.py normally generates it first

a = Analysis(
    ["game/main.py"],
    pathex=["game"],                 # the game's modules import each other flatly
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Trim things pygame or the stdlib might drag in but the game never uses.
    excludes=[
        "numpy", "tkinter", "unittest", "pytest", "_pytest", "doctest",
        "pdb", "pydoc", "setuptools", "pip", "distutils",
        "email", "html", "http", "xml", "xmlrpc", "urllib.request",
        "sqlite3", "curses", "lib2to3", "multiprocessing",
        "PIL", "cv2", "matplotlib",
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BlockAdventure",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                   # no terminal window behind the game
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)
