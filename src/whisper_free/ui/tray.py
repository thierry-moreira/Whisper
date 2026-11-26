"""System tray icon and context menu (pystray + Pillow).

The tray lives in its own thread (pystray requirement). Menu callbacks are
plain callables provided by :class:`~whisper_free.core.controller.Controller`,
so this module has no knowledge of the audio/transcription stack.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from whisper_free.config.constants import APP_NAME
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.tray")

ICON_SIZE = 64


@dataclass
class TrayCallbacks:
    """Actions the tray menu can trigger."""

    on_toggle_enabled: Callable[[], None]
    on_toggle_overlay: Callable[[], None]
    on_open_config: Callable[[], None]
    on_configure_openai: Callable[[], None]
    on_open_logs: Callable[[], None]
    on_toggle_autostart: Callable[[], None]
    on_quit: Callable[[], None]
    is_enabled: Callable[[], bool]
    is_overlay_enabled: Callable[[], bool]
    is_autostart_enabled: Callable[[], bool]
    is_openai_configured: Callable[[], bool]


def build_icon_image(enabled: bool = True):
    """Draw the tray icon (mic glyph on a rounded disc) with Pillow."""
    from PIL import Image, ImageDraw

    size = ICON_SIZE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    bg = (79, 140, 255, 255) if enabled else (110, 116, 128, 255)
    draw.ellipse((2, 2, size - 2, size - 2), fill=bg)

    # Microphone body
    body_w, body_h = 16, 24
    cx, cy = size // 2, size // 2 - 4
    draw.rounded_rectangle(
        (cx - body_w // 2, cy - body_h // 2, cx + body_w // 2, cy + body_h // 2),
        radius=8,
        fill=(255, 255, 255, 255),
    )
    # Stand + base
    draw.arc(
        (cx - 14, cy - 10, cx + 14, cy + 16),
        start=0,
        end=180,
        fill=(255, 255, 255, 255),
        width=4,
    )
    draw.line((cx, cy + 16, cx, cy + 22), fill=(255, 255, 255, 255), width=4)
    draw.line((cx - 9, cy + 22, cx + 9, cy + 22), fill=(255, 255, 255, 255), width=4)
    return image


class TrayIcon:
    """Owns the pystray icon and its menu."""

    def __init__(self, callbacks: TrayCallbacks) -> None:
        self._callbacks = callbacks
        self._icon: Any | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        """Create the icon and run it in a daemon thread."""
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem(
                lambda _: "Desativar" if self._callbacks.is_enabled() else "Ativar",
                lambda: self._callbacks.on_toggle_enabled(),
            ),
            pystray.MenuItem(
                lambda _: (
                    "Ocultar indicador"
                    if self._callbacks.is_overlay_enabled()
                    else "Mostrar indicador"
                ),
                lambda: self._callbacks.on_toggle_overlay(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda _: (
                    "Desativar início com Windows"
                    if self._callbacks.is_autostart_enabled()
                    else "Iniciar com Windows"
                ),
                lambda: self._callbacks.on_toggle_autostart(),
            ),
            pystray.MenuItem(
                lambda _: (
                    "Configurar API OpenAI…"
                    if self._callbacks.is_openai_configured()
                    else "Configurar API OpenAI (chave pendente)…"
                ),
                lambda: self._callbacks.on_configure_openai(),
            ),
            pystray.MenuItem(
                "Abrir configurações (.env)", lambda: self._callbacks.on_open_config()
            ),
            pystray.MenuItem("Abrir pasta de logs", lambda: self._callbacks.on_open_logs()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", lambda: self._callbacks.on_quit()),
        )
        self._icon = pystray.Icon(
            APP_NAME,
            icon=build_icon_image(self._callbacks.is_enabled()),
            title=APP_NAME,
            menu=menu,
        )
        self._thread = threading.Thread(
            target=self._icon.run, name="whisper-free-tray", daemon=True
        )
        self._thread.start()
        logger.info("System tray icon started")

    def refresh(self) -> None:
        """Redraw the icon to reflect the enabled state."""
        if self._icon is None:
            return
        try:
            self._icon.icon = build_icon_image(self._callbacks.is_enabled())
            self._icon.update_menu()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Tray refresh failed: {exc}")

    def notify(self, message: str, title: str = APP_NAME) -> None:
        """Show a balloon notification (best-effort)."""
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title)
        except Exception as exc:  # pragma: no cover - not supported everywhere
            logger.debug(f"Tray notify failed: {exc}")

    def stop(self) -> None:
        if self._icon is None:
            return
        try:
            self._icon.stop()
            logger.info("System tray icon stopped")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Tray stop failed: {exc}")
        finally:
            self._icon = None
