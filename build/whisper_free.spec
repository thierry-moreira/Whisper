# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file build for Whisper Free.

Build from the repository root:
    pyinstaller --clean --noconfirm build/whisper_free.spec
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ASSETS = ROOT / "assets"

hiddenimports = [
    "ctranslate2",
    "faster_whisper",
    "language_tool_python",
    "pystray",
    "PIL",
    "keyboard",
    "pyperclip",
    "sounddevice",
    "numpy",
    "pydantic",
    "pydantic_settings",
    "loguru",
]

datas = [(str(ASSETS), "assets")] if ASSETS.is_dir() else []
icon = ASSETS / "icon.ico"

# CTranslate2 loads cuBLAS/cuDNN dynamically, so PyInstaller cannot discover
# them.  Bundle the pip-installed NVIDIA runtime when it is present.
binaries = []
try:
    import ctranslate2

    nvidia_root = Path(ctranslate2.__file__).resolve().parent.parent / "nvidia"
    for dll in nvidia_root.glob("*/bin/*.dll"):
        binaries.append((str(dll), f"nvidia/{dll.parent.parent.name}/bin"))
except Exception:
    pass

a = Analysis(
    [str(SRC / "whisper_free" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests", "tkinter.test"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WhisperFree",
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
    icon=str(icon) if icon.is_file() else None,
)
