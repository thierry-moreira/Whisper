"""Text injection into the focused window.

Two strategies are supported (configurable via ``injector.mode``):

* ``paste``  — save clipboard → set text → Ctrl+V → restore clipboard.
  Fastest and 100% unicode-safe (accents, emoji, newlines).
* ``type``   — native ``SendInput`` with ``KEYEVENTF_UNICODE``, character by
  character. Does not touch the clipboard, slightly slower.

Both the clipboard and the key sender are injectable so unit tests can run
without Windows APIs.
"""

from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from typing import Protocol

from whisper_free.config.settings import InjectorSettings
from whisper_free.utils.helpers import is_windows
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.injector")

# ---------------------------------------------------------------------------
# Windows SendInput constants / structures (computed lazily, Windows only)
# ---------------------------------------------------------------------------
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_V = 0x56
INPUT_KEYBOARD = 1


class Clipboard(Protocol):
    """Clipboard abstraction (pyperclip in production)."""

    def paste(self) -> str: ...

    def copy(self, text: str) -> None: ...


class KeySender(Protocol):
    """Keyboard abstraction (SendInput in production)."""

    def send_ctrl_v(self) -> None: ...

    def type_text(self, text: str, interval_s: float) -> None: ...


@dataclass
class InjectResult:
    """Outcome of an injection attempt."""

    text: str = ""
    method: str = ""
    elapsed_s: float = 0.0
    success: bool = True
    error: str | None = None


class _PyperclipClipboard:
    """Thin wrapper so pyperclip is imported only when needed."""

    def paste(self) -> str:
        import pyperclip

        return pyperclip.paste()

    def copy(self, text: str) -> None:
        import pyperclip

        pyperclip.copy(text)


class _SendInputKeySender:
    """Windows-native key sender using user32!SendInput."""

    def __init__(self) -> None:
        if not is_windows():  # pragma: no cover - guarded by callers
            raise RuntimeError("SendInput is only available on Windows")
        self._user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        self._build_structs()

    def _build_structs(self) -> None:
        PUL = ctypes.POINTER(ctypes.c_ulong)

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL),
            ]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL),
            ]

        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [
                ("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_ushort),
                ("wParamH", ctypes.c_ushort),
            ]

        class _Union(ctypes.Union):
            _fields_ = [
                ("ki", KEYBDINPUT),
                ("mi", MOUSEINPUT),
                ("hi", HARDWAREINPUT),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("u", _Union)]

        self._INPUT = INPUT
        self._KEYBDINPUT = KEYBDINPUT
        self._Union = _Union

    def _send(self, inputs: list) -> None:
        n = len(inputs)
        array = (self._INPUT * n)(*inputs)
        sent = self._user32.SendInput(n, ctypes.byref(array), ctypes.sizeof(self._INPUT))
        if sent != n:
            raise OSError(f"SendInput delivered {sent}/{n} events")

    def _key_event(self, vk: int = 0, scan: int = 0, flags: int = 0):
        extra = ctypes.c_ulong(0)
        kb = self._KEYBDINPUT(
            wVk=vk,
            wScan=scan,
            dwFlags=flags,
            time=0,
            dwExtraInfo=ctypes.pointer(extra),
        )
        return self._INPUT(type=INPUT_KEYBOARD, u=self._Union(ki=kb))

    def send_ctrl_v(self) -> None:
        events = [
            self._key_event(vk=VK_CONTROL),
            self._key_event(vk=VK_V),
            self._key_event(vk=VK_V, flags=KEYEVENTF_KEYUP),
            self._key_event(vk=VK_CONTROL, flags=KEYEVENTF_KEYUP),
        ]
        self._send(events)

    def type_text(self, text: str, interval_s: float = 0.001) -> None:
        for char in text:
            for code_unit in self._utf16_units(char):
                events = [
                    self._key_event(scan=code_unit, flags=KEYEVENTF_UNICODE),
                    self._key_event(scan=code_unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
                ]
                self._send(events)
                if interval_s > 0:
                    time.sleep(interval_s)

    @staticmethod
    def _utf16_units(char: str) -> list[int]:
        """Return UTF-16 code units (handles non-BMP chars via surrogates)."""
        encoded = char.encode("utf-16-le")
        return [int.from_bytes(encoded[i : i + 2], "little") for i in range(0, len(encoded), 2)]


class TextInjector:
    """Delivers the final text to whatever window has focus."""

    def __init__(
        self,
        settings: InjectorSettings,
        clipboard: Clipboard | None = None,
        key_sender: KeySender | None = None,
    ) -> None:
        self._settings = settings
        self._clipboard = clipboard
        self._key_sender = key_sender

    # ------------------------------------------------------------------ API
    def inject(self, text: str) -> InjectResult:
        """Inject ``text`` using the configured strategy."""
        started = time.perf_counter()
        clean = (text or "").strip()
        if not clean:
            return InjectResult(text=text, method="none", success=True)

        method: str = self._settings.mode
        try:
            if self._settings.pre_inject_delay_s > 0:
                time.sleep(self._settings.pre_inject_delay_s)
            if method == "type":
                method = self._inject_type(clean)
            else:
                try:
                    method = self._inject_paste(clean)
                except Exception as exc:
                    if not self._settings.fallback_to_type:
                        raise
                    logger.warning(f"Clipboard paste failed ({exc}) — typing the text directly")
                    method = self._inject_type(clean)
        except Exception as exc:
            logger.exception("Text injection failed")
            return InjectResult(
                text=clean,
                method=method,
                elapsed_s=time.perf_counter() - started,
                success=False,
                error=str(exc),
            )

        elapsed = time.perf_counter() - started
        logger.info(f"Injected {len(clean)} chars via {method} in {elapsed * 1000:.0f}ms")
        return InjectResult(text=clean, method=method, elapsed_s=elapsed, success=True)

    # ------------------------------------------------------------- strategies
    def _inject_paste(self, text: str) -> str:
        clipboard = self._clipboard or _PyperclipClipboard()
        key_sender = self._key_sender or self._default_key_sender()

        previous = ""
        if self._settings.restore_clipboard:
            try:
                previous = clipboard.paste()
            except Exception as exc:  # clipboard can transiently fail
                logger.debug(f"Could not read clipboard: {exc}")
        clipboard.copy(text)
        time.sleep(0.02)  # let the clipboard settle before pasting
        key_sender.send_ctrl_v()
        if self._settings.restore_clipboard:
            time.sleep(0.25)  # give the target app time to consume the paste
            try:
                clipboard.copy(previous)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"Could not restore clipboard: {exc}")
        return "paste"

    def _inject_type(self, text: str) -> str:
        key_sender = self._key_sender or self._default_key_sender()
        key_sender.type_text(text, self._settings.char_interval_s)
        return "type"

    def _default_key_sender(self) -> KeySender:
        if not is_windows():
            raise RuntimeError("Built-in key injection requires Windows")
        return _SendInputKeySender()
