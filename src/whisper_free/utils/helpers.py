"""Small, dependency-light helpers shared across the app."""

from __future__ import annotations

import ctypes
import sys
import threading
from pathlib import Path

from whisper_free.config.constants import APP_MUTEX_NAME

_single_instance_handle: int | None = None


def is_windows() -> bool:
    """True when running on Windows."""
    return sys.platform.startswith("win")


def is_frozen() -> bool:
    """True when running from a PyInstaller/Nuitka bundle."""
    return bool(getattr(sys, "frozen", False))


def pythonw_executable() -> str:
    """Return pythonw.exe (windowless) when available, else the current exe."""
    exe = Path(sys.executable)
    if is_frozen():
        return str(exe)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def launcher_script_path() -> Path:
    """Path to the .pyw launcher used for autostart in dev mode."""
    from whisper_free.config.constants import PROJECT_ROOT

    return PROJECT_ROOT / "scripts" / "whisper_free_launcher.pyw"


def acquire_single_instance_lock(name: str = APP_MUTEX_NAME) -> bool:
    """Try to hold a Windows named mutex.

    Returns True when this process is the only instance. On non-Windows
    platforms always returns True.
    """
    global _single_instance_handle
    if not is_windows():
        return True
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, False, name)
    last_error = kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    if last_error == ERROR_ALREADY_EXISTS:
        if handle:
            kernel32.CloseHandle(handle)
        return False
    _single_instance_handle = handle
    return True


def release_single_instance_lock() -> None:
    """Release the mutex acquired by :func:`acquire_single_instance_lock`."""
    global _single_instance_handle
    if _single_instance_handle and is_windows():
        ctypes.windll.kernel32.CloseHandle(_single_instance_handle)  # type: ignore[attr-defined]
        _single_instance_handle = None


class AtomicFlag:
    """A tiny thread-safe boolean flag."""

    def __init__(self, initial: bool = False) -> None:
        self._value = initial
        self._lock = threading.Lock()

    def set(self, value: bool) -> None:
        with self._lock:
            self._value = value

    def get(self) -> bool:
        with self._lock:
            return self._value

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return self.get()


def clamp(value: float, low: float, high: float) -> float:
    """Clamp ``value`` into the inclusive ``[low, high]`` range."""
    return max(low, min(high, value))
