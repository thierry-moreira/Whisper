"""Global hotkey registration (push-to-talk and toggle).

Uses the ``keyboard`` library, whose import is deferred and replaceable via
the ``backend`` parameter so unit tests never touch real hooks.

Three bindings are managed:

* ``trigger``         — local (GPU) dictation
* ``cloud_trigger``   — OpenAI API dictation
* ``toggle_enabled``  — enables/disables the whole assistant

Both dictation bindings share the hold/toggle mode but keep independent
debounce and active state, so releasing one never stops the other.
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from whisper_free.config.constants import HOTKEY_PRESS_DEBOUNCE_S
from whisper_free.config.settings import HotkeySettings
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.hotkey")

_LOCAL = "local"
_CLOUD = "cloud"


class HotkeyBackend(Protocol):
    """Minimal surface of the ``keyboard`` module that we depend on."""

    def add_hotkey(
        self, hotkey: str, callback: Callable[[], None], **kwargs
    ) -> Callable[[], None]: ...

    def remove_hotkey(self, handle: Callable[[], None]) -> None: ...


@dataclass
class HotkeyCallbacks:
    """Callbacks invoked from the keyboard listener thread."""

    on_press: Callable[[], None]
    on_release: Callable[[], None]
    on_toggle_enabled: Callable[[], None]
    on_cloud_press: Callable[[], None] | None = None
    on_cloud_release: Callable[[], None] | None = None


class HotkeyManager:
    """Registers/unregisters the global hotkeys with debouncing."""

    def __init__(
        self,
        settings: HotkeySettings,
        callbacks: HotkeyCallbacks,
        backend: HotkeyBackend | None = None,
    ) -> None:
        self._settings = settings
        self._callbacks = callbacks
        self._backend = backend
        # ``keyboard.add_hotkey`` returns a remover callable; that is the
        # only value ``remove_hotkey`` accepts.
        self._handles: list[Callable[[], None]] = []
        self._lock = threading.Lock()
        self._last_press: dict[str, float] = {_LOCAL: 0.0, _CLOUD: 0.0}
        self._last_release: dict[str, float] = {_LOCAL: 0.0, _CLOUD: 0.0}
        self._active: dict[str, bool] = {_LOCAL: False, _CLOUD: False}
        self._registered = False

    # ------------------------------------------------------------------ API
    @property
    def is_registered(self) -> bool:
        return self._registered

    def register(self) -> None:
        """Wire the global hooks. Idempotent."""
        with self._lock:
            if self._registered:
                return
            backend = self._backend or self._load_backend()
            suppress = self._settings.suppress
            try:
                if self._settings.mode == "hold":
                    self._register_hold(backend, _LOCAL, self._settings.trigger, suppress)
                    if self._cloud_enabled:
                        self._register_hold(backend, _CLOUD, self._settings.cloud_trigger, suppress)
                else:  # toggle
                    self._register_toggle(backend, _LOCAL, self._settings.trigger, suppress)
                    if self._cloud_enabled:
                        self._register_toggle(
                            backend, _CLOUD, self._settings.cloud_trigger, suppress
                        )
                self._handles.append(
                    backend.add_hotkey(
                        self._settings.toggle_enabled,
                        self._callbacks.on_toggle_enabled,
                        suppress=False,
                    )
                )
            except Exception as exc:
                logger.error(f"Failed to register hotkeys: {exc}")
                self._remove_handles_locked(backend)
                raise
            self._registered = True
            logger.info(
                "Hotkeys registered: trigger='{}' (mode={}), cloud-trigger='{}', "
                "toggle-enabled='{}'",
                self._settings.trigger,
                self._settings.mode,
                self._settings.cloud_trigger if self._cloud_enabled else "(disabled)",
                self._settings.toggle_enabled,
            )

    def unregister(self) -> None:
        """Remove all hooks. Safe to call when not registered."""
        with self._lock:
            if not self._registered:
                return
            backend = self._backend or self._load_backend()
            self._remove_handles_locked(backend)
            self._registered = False
            logger.info("Hotkeys unregistered")

    def _remove_handles_locked(self, backend: HotkeyBackend) -> None:
        """Remove every registered hook (caller already holds the lock)."""
        for handle in self._handles:
            try:
                backend.remove_hotkey(handle)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"remove_hotkey failed: {exc}")
        self._handles.clear()

    # ------------------------------------------------------------- handlers
    @property
    def _cloud_enabled(self) -> bool:
        return bool(self._settings.cloud_trigger and self._callbacks.on_cloud_press)

    def _register_hold(
        self,
        backend: HotkeyBackend,
        mode: str,
        hotkey: str,
        suppress: bool,
    ) -> None:
        self._handles.append(
            backend.add_hotkey(
                hotkey,
                functools.partial(self._guarded_press, mode),
                suppress=suppress,
            )
        )
        self._handles.append(
            backend.add_hotkey(
                hotkey,
                functools.partial(self._guarded_release, mode),
                suppress=suppress,
                trigger_on_release=True,
            )
        )

    def _register_toggle(
        self,
        backend: HotkeyBackend,
        mode: str,
        hotkey: str,
        suppress: bool,
    ) -> None:
        self._handles.append(
            backend.add_hotkey(
                hotkey,
                functools.partial(self._guarded_toggle, mode),
                suppress=suppress,
            )
        )

    def _guarded_press(self, mode: str) -> None:
        now = time.monotonic()
        if now - self._last_press[mode] < HOTKEY_PRESS_DEBOUNCE_S:
            return  # key-repeat / duplicate event
        self._last_press[mode] = now
        self._active[mode] = True
        callback = self._callback(mode, "press")
        if callback is not None:
            self._safe(callback)

    def _guarded_release(self, mode: str) -> None:
        if not self._active[mode]:
            return
        now = time.monotonic()
        if now - self._last_release[mode] < HOTKEY_PRESS_DEBOUNCE_S:
            return
        self._last_release[mode] = now
        self._active[mode] = False
        callback = self._callback(mode, "release")
        if callback is not None:
            self._safe(callback)

    def _guarded_toggle(self, mode: str) -> None:
        now = time.monotonic()
        if now - self._last_press[mode] < HOTKEY_PRESS_DEBOUNCE_S:
            return
        self._last_press[mode] = now
        if self._active[mode]:
            self._active[mode] = False
            callback = self._callback(mode, "release")
        else:
            self._active[mode] = True
            callback = self._callback(mode, "press")
        if callback is not None:
            self._safe(callback)

    def _callback(self, mode: str, event: str) -> Callable[[], None] | None:
        if mode == _CLOUD:
            return (
                self._callbacks.on_cloud_press
                if event == "press"
                else self._callbacks.on_cloud_release
            )
        return self._callbacks.on_press if event == "press" else self._callbacks.on_release

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _safe(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception as exc:  # pragma: no cover - keep listener alive
            logger.exception(f"Hotkey callback raised: {exc}")

    @staticmethod
    def _load_backend() -> HotkeyBackend:
        import keyboard  # deferred: needs a real Windows session

        return keyboard


def parse_hotkey(hotkey: str) -> list[str]:
    """Split a hotkey string into normalised key names."""
    return [part.strip().lower() for part in hotkey.split("+") if part.strip()]
