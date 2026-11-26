"""Windows auto-start via the per-user Run registry key.

Dev mode registers ``pythonw.exe`` + the ``.pyw`` launcher (no console
window).  Frozen mode registers the packaged executable directly with
``--silent``.
"""

from __future__ import annotations

from pathlib import Path

from whisper_free.config.constants import APP_SLUG
from whisper_free.utils.helpers import (
    is_frozen,
    is_windows,
    launcher_script_path,
    pythonw_executable,
)
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.startup")

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


class WindowsStartup:
    """Manage the ``HKCU\\...\\Run`` entry for this application."""

    def __init__(self, value_name: str = APP_SLUG) -> None:
        self._value_name = value_name

    # ------------------------------------------------------------------ API
    def is_enabled(self) -> bool:
        """True when the Run entry exists for the current user."""
        if not is_windows():
            return False
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, self._value_name)
                return True
        except FileNotFoundError:
            return False
        except OSError as exc:  # pragma: no cover - permissions etc.
            logger.warning(f"Could not read startup registry entry: {exc}")
            return False

    def enable(self) -> bool:
        """Create/refresh the Run entry. Returns True on success."""
        if not is_windows():
            logger.warning("Auto-start is only supported on Windows")
            return False
        import winreg

        command = self.build_command()
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, self._value_name, 0, winreg.REG_SZ, command)
            logger.info(f"Auto-start enabled: {command}")
            return True
        except OSError as exc:
            logger.error(f"Failed to enable auto-start: {exc}")
            return False

    def disable(self) -> bool:
        """Remove the Run entry. Returns True on success (or when absent)."""
        if not is_windows():
            return False
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, self._value_name)
            logger.info("Auto-start disabled")
            return True
        except FileNotFoundError:
            return True
        except OSError as exc:  # pragma: no cover - defensive
            logger.error(f"Failed to disable auto-start: {exc}")
            return False

    def build_command(self) -> str:
        """Return the command line that Windows will launch at login."""
        if is_frozen():
            exe = Path(pythonw_executable())
            return f'"{exe}" --silent'
        launcher = launcher_script_path()
        if launcher.is_file():
            return f'"{pythonw_executable()}" "{launcher}"'
        return f'"{pythonw_executable()}" -m whisper_free --silent'

    def set_enabled(self, enabled: bool) -> bool:
        """Convenience: enable or disable depending on ``enabled``."""
        return self.enable() if enabled else self.disable()
