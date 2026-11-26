"""Expose pip-installed NVIDIA CUDA runtime DLLs to CTranslate2 on Windows.

The ``nvidia-cublas-cu12`` and ``nvidia-cudnn-cu12`` wheels ship their DLLs
inside ``site-packages/nvidia/<component>/bin``.  Windows does not search
those folders by default, so CTranslate2 fails with::

    Library cublas64_12.dll is not found or cannot be loaded

:func:`register_nvidia_dlls` adds them to the process DLL search path once.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.cuda")

_COMPONENTS = ("cublas", "cudnn", "cuda_nvrtc")
_handles: list[object] = []
_registered: list[Path] | None = None


def _site_packages() -> Path | None:
    try:
        import ctranslate2
    except Exception:
        return None
    return Path(ctranslate2.__file__).resolve().parent.parent


def register_nvidia_dlls() -> list[Path]:
    """Add ``nvidia/*/bin`` to the DLL search path (idempotent, Windows only)."""
    global _registered
    if _registered is not None:
        return _registered

    _registered = []
    if sys.platform != "win32":
        return _registered

    site = _site_packages()
    if site is None:
        return _registered

    for component in _COMPONENTS:
        bin_dir = site / "nvidia" / component / "bin"
        if not bin_dir.is_dir():
            continue
        try:
            _handles.append(os.add_dll_directory(str(bin_dir)))
        except OSError as exc:  # pragma: no cover - defensive
            logger.debug(f"Could not register {bin_dir}: {exc}")
            continue
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        _registered.append(bin_dir)

    if _registered:
        logger.debug(f"NVIDIA DLL directories registered: {[str(p) for p in _registered]}")
    return _registered
