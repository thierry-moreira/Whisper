"""Compact on-screen status capsule (whisper-style overlay).

A frameless, always-on-top pill anchored to the bottom of the screen, drawn
with tkinter's Canvas:

* **listening**  — pulsing record dot, live level bars and elapsed time
* **processing** — rotating spinner + "Processando…"
* **success**    — green check + preview of the injected text
* **error**      — red cross + short message

Thread-safety: public methods may be called from any thread; they enqueue
actions which the UI thread drains in :meth:`_poll_queue` (the only place Tk
widgets are touched).
"""

from __future__ import annotations

import contextlib
import math
import queue
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from tkinter import font as tkfont

from whisper_free.config import constants
from whisper_free.config.settings import OverlaySettings
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.overlay")

MAGIC_BG = "#010203"  # key colour made transparent via -transparentcolor
PANEL_BG = "#0a0a0d"
PANEL_BORDER = "#26262d"
PANEL_GLOW = "#2a1216"
ACCENT = "#d6d6dc"
ACCENT_DIM = "#8f8f98"
SUCCESS = "#4ade80"
SUCCESS_BG = "#0e1a14"
SUCCESS_BORDER = "#1f3d2e"
ERROR = "#ff5c5c"
ERROR_BG = "#1e0e10"
ERROR_BORDER = "#4a1a1e"
RECORD = "#ff3b3b"
TEXT_FG = "#ececf1"
TEXT_MUTED = "#8b8b94"
TEXT_ERROR = "#ffb4b4"
CLOUD = "#8ab4ff"
CLOUD_BG = "#101824"
CLOUD_BORDER = "#27405f"

FONT_FAMILY = "Segoe UI"
CENTER_Y = constants.OVERLAY_HEIGHT // 2
ICON_CX = 24
BARS_X = 42
BAR_COUNT = 13
BAR_GAP = 5
STATUS_X = BARS_X + (BAR_COUNT - 1) * BAR_GAP + 12
TEXT_X = 42
RIGHT_PAD = 14


class OverlayState(Enum):
    HIDDEN = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SUCCESS = auto()
    ERROR = auto()


@dataclass
class _Frame:
    """Internal snapshot the canvas renderer reads."""

    state: OverlayState = OverlayState.HIDDEN
    message: str = ""
    cloud: bool = False


class OverlayWindow:
    """The visual indicator window (owns the Tk main loop)."""

    def __init__(self, settings: OverlaySettings, root: tk.Tk | None = None) -> None:
        self._settings = settings
        self._queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._frame = _Frame()
        self._tick_count = 0
        self._ticking = False
        self._listening_started = 0.0
        self._hide_job: str | None = None
        self._openai_dialog: tk.Toplevel | None = None
        self._running = False

        self.root = root or tk.Tk()
        self.root.withdraw()  # Tk root stays hidden; only the overlay shows

        self._font_status = tkfont.Font(family=FONT_FAMILY, size=9, weight="bold")
        self._font_body = tkfont.Font(family=FONT_FAMILY, size=9)
        self._font_timer = tkfont.Font(family=FONT_FAMILY, size=8)
        self._font_badge = tkfont.Font(family=FONT_FAMILY, size=7, weight="bold")

        self._win = tk.Toplevel(self.root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.98)
        try:
            self._win.attributes("-transparentcolor", MAGIC_BG)
        except tk.TclError:  # pragma: no cover - non-Windows fallback
            logger.debug("-transparentcolor unsupported on this platform")
        self._win.configure(bg=MAGIC_BG)

        self._canvas = tk.Canvas(
            self._win,
            width=constants.OVERLAY_WIDTH,
            height=constants.OVERLAY_HEIGHT,
            bg=MAGIC_BG,
            highlightthickness=0,
        )
        self._canvas.pack()
        self._win.withdraw()
        self._draw()

    # ------------------------------------------------------------------ API
    def show_listening(self, cloud: bool = False) -> None:
        self._post(lambda: self._set_state(OverlayState.LISTENING, "Ouvindo", cloud=cloud))

    def show_processing(self, cloud: bool = False) -> None:
        self._post(lambda: self._set_state(OverlayState.PROCESSING, "Processando…", cloud=cloud))

    def show_success(self, text: str) -> None:
        preview = text if len(text) <= 140 else text[:139] + "…"
        message = preview if preview else "Concluído"
        self._post(lambda: self._set_state(OverlayState.SUCCESS, message, auto_hide=True))

    def show_error(self, message: str) -> None:
        short = message if len(message) <= 140 else message[:139] + "…"
        self._post(lambda: self._set_state(OverlayState.ERROR, short, auto_hide=True))

    def hide(self) -> None:
        self._post(lambda: self._set_state(OverlayState.HIDDEN, ""))

    def show_openai_settings(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        on_save: Callable[[str, str, str], str | None],
    ) -> None:
        """Open the OpenAI key/model dialog on the Tk thread."""
        self._post(lambda: self._open_openai_dialog(api_key, model, base_url, on_save))

    def run(self) -> None:
        """Start the Tk main loop (blocking — call from the main thread)."""
        self._running = True
        self.root.after(30, self._poll_queue)
        self.root.mainloop()

    def stop(self) -> None:
        """Ask the main loop to exit (callable from any thread)."""
        self._post(self.root.quit)

    # -------------------------------------------------------------- internal
    def _open_openai_dialog(
        self,
        api_key: str,
        model: str,
        base_url: str,
        on_save: Callable[[str, str, str], str | None],
    ) -> None:
        if self._openai_dialog is not None and self._openai_dialog.winfo_exists():
            self._raise_openai_dialog()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("OpenAI — Whisper Free")
        dialog.configure(bg=PANEL_BG)
        dialog.resizable(False, False)
        # NOTE: never call dialog.transient(self.root) here — the Tk root is
        # withdrawn (hidden) and Windows hides windows owned by a hidden owner,
        # which made the dialog open invisibly.  ``-topmost`` keeps it above the
        # overlay pill instead.
        dialog.attributes("-topmost", True)
        dialog.protocol("WM_DELETE_WINDOW", self._close_openai_dialog)
        self._openai_dialog = dialog

        width, height = 560, 390
        screen_w = dialog.winfo_screenwidth()
        screen_h = dialog.winfo_screenheight()
        dialog.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{(screen_h - height) // 2}")

        body = tk.Frame(dialog, bg=PANEL_BG, padx=24, pady=18)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="Transcrição via API OpenAI",
            bg=PANEL_BG,
            fg=TEXT_FG,
            font=(FONT_FAMILY, 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text=(
                "Usada pelo segundo atalho. A chave fica salva apenas no .env local "
                "e nunca aparece nos logs."
            ),
            bg=PANEL_BG,
            fg=TEXT_MUTED,
            font=(FONT_FAMILY, 9),
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(4, 14))

        key_var = tk.StringVar(value=api_key)
        model_var = tk.StringVar(value=model)
        base_var = tk.StringVar(value=base_url)
        error_var = tk.StringVar()

        def field_label(label: str) -> None:
            tk.Label(
                body,
                text=label,
                bg=PANEL_BG,
                fg=TEXT_MUTED,
                font=(FONT_FAMILY, 9),
                anchor="w",
            ).pack(fill="x", pady=(0, 4))

        def field_entry(variable: tk.StringVar, *, show: str = "") -> tk.Entry:
            entry = tk.Entry(
                body,
                textvariable=variable,
                show=show,
                bg="#141419",
                fg=TEXT_FG,
                insertbackground=TEXT_FG,
                relief="flat",
                highlightthickness=1,
                highlightbackground=PANEL_BORDER,
                highlightcolor=ACCENT_DIM,
                font=(FONT_FAMILY, 9),
            )
            entry.pack(fill="x", ipady=5, pady=(0, 12))
            return entry

        field_label("Chave da API")
        key_row = tk.Frame(body, bg=PANEL_BG)
        key_row.pack(fill="x", pady=(0, 12))
        key_entry = tk.Entry(
            key_row,
            textvariable=key_var,
            show="•",
            bg="#141419",
            fg=TEXT_FG,
            insertbackground=TEXT_FG,
            relief="flat",
            highlightthickness=1,
            highlightbackground=PANEL_BORDER,
            highlightcolor=ACCENT_DIM,
            font=(FONT_FAMILY, 9),
        )
        key_entry.pack(side="left", fill="x", expand=True, ipady=5)
        show_var = tk.BooleanVar(value=False)

        def toggle_key_visibility() -> None:
            key_entry.configure(show="" if show_var.get() else "•")

        tk.Checkbutton(
            key_row,
            text="Mostrar",
            variable=show_var,
            command=toggle_key_visibility,
            bg=PANEL_BG,
            fg=TEXT_MUTED,
            activebackground=PANEL_BG,
            activeforeground=TEXT_FG,
            selectcolor="#141419",
            highlightthickness=0,
            bd=0,
            font=(FONT_FAMILY, 8),
        ).pack(side="left", padx=(10, 0))

        field_label("Modelo")
        field_entry(model_var)
        tk.Label(
            body,
            text="Modelos: " + ", ".join(constants.OPENAI_MODELS),
            bg=PANEL_BG,
            fg=TEXT_MUTED,
            font=(FONT_FAMILY, 8),
            anchor="w",
        ).pack(fill="x", pady=(0, 12))

        field_label("Endpoint")
        field_entry(base_var)

        tk.Label(
            body,
            textvariable=error_var,
            bg=PANEL_BG,
            fg=TEXT_ERROR,
            font=(FONT_FAMILY, 9),
            anchor="w",
            justify="left",
        ).pack(fill="x")

        buttons = tk.Frame(body, bg=PANEL_BG)
        buttons.pack(fill="x", pady=(16, 0))

        def save() -> None:
            try:
                error = on_save(key_var.get(), model_var.get(), base_var.get())
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"OpenAI save callback failed: {exc}")
                error = "Falha ao salvar a configuração."
            if error:
                error_var.set(error)
                return
            self._close_openai_dialog()

        def button(label: str, command: Callable[[], None], *, primary: bool = False) -> tk.Button:
            return tk.Button(
                buttons,
                text=label,
                command=command,
                bg="#2b4a7a" if primary else "#1b1b22",
                fg=TEXT_FG,
                activebackground="#35598f" if primary else "#25252e",
                activeforeground=TEXT_FG,
                relief="flat",
                bd=0,
                padx=16,
                pady=6,
                cursor="hand2",
                font=(FONT_FAMILY, 9),
            )

        button("Salvar", save, primary=True).pack(side="right")
        button("Cancelar", self._close_openai_dialog).pack(side="right", padx=(0, 8))

        dialog.bind("<Escape>", lambda _event: self._close_openai_dialog())
        dialog.bind("<Return>", lambda _event: save())
        dialog.update_idletasks()
        dialog.deiconify()
        dialog.lift()
        dialog.attributes("-topmost", True)
        with contextlib.suppress(Exception):
            dialog.grab_set()
        key_entry.focus_force()
        logger.debug("OpenAI settings dialog opened")

    def _raise_openai_dialog(self) -> None:
        dialog = self._openai_dialog
        if dialog is None or not dialog.winfo_exists():
            return
        dialog.deiconify()
        dialog.lift()
        dialog.attributes("-topmost", True)
        dialog.focus_force()

    def _close_openai_dialog(self) -> None:
        dialog, self._openai_dialog = self._openai_dialog, None
        if dialog is not None:
            with contextlib.suppress(Exception):
                dialog.grab_release()
            with contextlib.suppress(Exception):
                dialog.destroy()

    def _post(self, action: Callable[[], None]) -> None:
        self._queue.put(action)

    def _poll_queue(self) -> None:
        try:
            while True:
                action = self._queue.get_nowait()
                try:
                    action()
                except Exception as exc:  # pragma: no cover - UI must not die
                    logger.exception(f"Overlay action failed: {exc}")
        except queue.Empty:
            pass
        if self._running:
            self.root.after(30, self._poll_queue)

    def _set_state(
        self,
        state: OverlayState,
        message: str,
        auto_hide: bool = False,
        cloud: bool = False,
    ) -> None:
        previous = self._frame.state
        self._frame = _Frame(state=state, message=message, cloud=cloud)
        if state == OverlayState.LISTENING and previous != OverlayState.LISTENING:
            self._listening_started = time.monotonic()
        if self._hide_job is not None:
            with contextlib.suppress(Exception):
                self.root.after_cancel(self._hide_job)
            self._hide_job = None

        if state == OverlayState.HIDDEN:
            self._win.withdraw()
            return

        self._position_window()
        self._win.deiconify()
        self._win.lift()
        self._win.attributes("-topmost", True)
        self._draw()
        self._start_ticking()

        if auto_hide and self._settings.always_show_on_success_ms > 0:
            self._hide_job = self.root.after(
                self._settings.always_show_on_success_ms,
                lambda: self._set_state(OverlayState.HIDDEN, ""),
            )

    def _start_ticking(self) -> None:
        if (
            self._frame.state in (OverlayState.LISTENING, OverlayState.PROCESSING)
            and not self._ticking
        ):
            self._ticking = True
            self._tick()

    def _tick(self) -> None:
        if self._frame.state not in (OverlayState.LISTENING, OverlayState.PROCESSING):
            self._ticking = False
            self._tick_count = 0
            return
        self._tick_count += 1
        self._draw()
        self.root.after(constants.OVERLAY_FPS_MS, self._tick)

    def _position_window(self) -> None:
        width = constants.OVERLAY_WIDTH
        height = constants.OVERLAY_HEIGHT
        self.root.update_idletasks()
        screen_w = self._win.winfo_screenwidth()
        screen_h = self._win.winfo_screenheight()
        position = self._settings.position

        if position == "center":
            x, y = (screen_w - width) // 2, (screen_h - height) // 2
        elif position == "bottom-center":
            x, y = (screen_w - width) // 2, screen_h - height - constants.OVERLAY_MARGIN
        elif position == "mouse":  # pragma: no cover - needs a real pointer
            px, py = self.root.winfo_pointerxy()
            x = min(max(px - width // 2, 0), screen_w - width)
            y = max(py - height - 24, 0)
        else:  # top-center
            x, y = (screen_w - width) // 2, constants.OVERLAY_MARGIN
        self._win.geometry(f"{width}x{height}+{x}+{y}")

    # ----------------------------------------------------------------- render
    def _draw(self) -> None:
        canvas = self._canvas
        canvas.delete("all")
        self._draw_panel(
            2,
            2,
            constants.OVERLAY_WIDTH - 3,
            constants.OVERLAY_HEIGHT - 3,
            radius=constants.OVERLAY_HEIGHT // 2 - 3,
        )

        state = self._frame.state
        if state == OverlayState.LISTENING:
            if self._frame.cloud:
                self._draw_api_badge(ICON_CX, CENTER_Y)
            else:
                self._draw_record_dot(ICON_CX, CENTER_Y)
            self._draw_bars(BARS_X, CENTER_Y)
            self._draw_status(self._frame.message, STATUS_X)
            self._draw_timer()
        elif state == OverlayState.PROCESSING:
            if self._frame.cloud:
                self._draw_api_badge(ICON_CX, CENTER_Y)
            else:
                self._draw_spinner(ICON_CX, CENTER_Y)
            self._draw_status(self._frame.message, TEXT_X)
        elif state == OverlayState.SUCCESS:
            self._draw_badge(ICON_CX, CENTER_Y, SUCCESS_BG, SUCCESS_BORDER)
            self._draw_check(ICON_CX, CENTER_Y)
            self._draw_message(TEXT_FG, quoted=True)
        elif state == OverlayState.ERROR:
            self._draw_badge(ICON_CX, CENTER_Y, ERROR_BG, ERROR_BORDER)
            self._draw_cross(ICON_CX, CENTER_Y)
            self._draw_message(TEXT_ERROR)

    def _draw_panel(self, x1: int, y1: int, x2: int, y2: int, radius: int) -> None:
        """Dark pill with a subtle warm glow rim and hairline border."""
        glow = _rounded_rect_points(x1 - 2, y1 - 2, x2 + 2, y2 + 2, radius + 2)
        self._canvas.create_polygon(glow, fill=PANEL_GLOW, outline="")
        points = _rounded_rect_points(x1, y1, x2, y2, radius)
        self._canvas.create_polygon(points, fill=PANEL_BG, outline=PANEL_BORDER, width=1)

    def _draw_record_dot(self, cx: int, cy: int) -> None:
        pulse = (math.sin(self._tick_count * 0.14) + 1) / 2
        outer = 10.5 + 1.2 * pulse
        canvas = self._canvas
        for radius, color in (
            (outer, _blend(PANEL_BG, RECORD, 0.10)),
            (outer - 2.0, _blend(PANEL_BG, RECORD, 0.22)),
            (outer - 4.0, _blend(PANEL_BG, RECORD, 0.40)),
        ):
            canvas.create_oval(
                cx - radius,
                cy - radius,
                cx + radius,
                cy + radius,
                fill=color,
                outline="",
            )
        canvas.create_oval(cx - 3.8, cy - 3.8, cx + 3.8, cy + 3.8, fill=RECORD, outline="")

    def _draw_api_badge(self, cx: int, cy: int) -> None:
        """Small blue “API” chip that marks cloud dictation."""
        points = _rounded_rect_points(cx - 13, cy - 8, cx + 13, cy + 8, 5)
        self._canvas.create_polygon(points, fill=CLOUD_BG, outline=CLOUD_BORDER, width=1)
        self._canvas.create_text(cx, cy, text="API", fill=CLOUD, font=self._font_badge)

    def _draw_bars(self, x: int, y: int) -> None:
        """Thirteen animated bars/dots in light grey, like a compact waveform."""
        canvas = self._canvas
        for index in range(BAR_COUNT):
            bar_x = x + index * BAR_GAP
            level = abs(math.sin(self._tick_count * 0.2 + index * 0.55))
            amplitude = 2.5 + 8.5 * level
            if index in (3, 7, 11):
                canvas.create_oval(
                    bar_x - 1.5,
                    y - 1.5,
                    bar_x + 1.5,
                    y + 1.5,
                    fill=ACCENT_DIM,
                    outline="",
                )
                continue
            canvas.create_line(
                bar_x,
                y - amplitude,
                bar_x,
                y + amplitude,
                fill=ACCENT,
                width=3,
                capstyle="round",
            )

    def _draw_spinner(self, cx: int, cy: int) -> None:
        canvas = self._canvas
        canvas.create_oval(cx - 9, cy - 9, cx + 9, cy + 9, outline=PANEL_BORDER, width=2)
        start = (self._tick_count * 10) % 360
        canvas.create_arc(
            cx - 9,
            cy - 9,
            cx + 9,
            cy + 9,
            start=start,
            extent=260,
            style="arc",
            outline=ACCENT,
            width=2.5,
        )

    def _draw_status(self, text: str, x: int) -> None:
        self._canvas.create_text(
            x,
            CENTER_Y,
            text=text,
            anchor="w",
            fill=TEXT_FG,
            font=self._font_status,
        )

    def _draw_timer(self) -> None:
        elapsed = max(0, int(time.monotonic() - self._listening_started))
        self._canvas.create_text(
            constants.OVERLAY_WIDTH - RIGHT_PAD,
            CENTER_Y,
            text=f"{elapsed // 60}:{elapsed % 60:02d}",
            anchor="e",
            fill=TEXT_MUTED,
            font=self._font_timer,
        )

    def _draw_message(self, fill: str, quoted: bool = False) -> None:
        if not self._frame.message:
            return
        max_width = constants.OVERLAY_WIDTH - TEXT_X - RIGHT_PAD
        if quoted:
            opening, closing = "“", "”"
            inner_width = max_width - self._font_body.measure(opening + closing)
            text = opening + _fit_text(self._frame.message, inner_width, self._font_body) + closing
        else:
            text = _fit_text(self._frame.message, max_width, self._font_body)
        self._canvas.create_text(
            TEXT_X,
            CENTER_Y,
            text=text,
            anchor="w",
            fill=fill,
            font=self._font_body,
        )

    def _draw_badge(self, cx: int, cy: int, fill: str, outline: str) -> None:
        radius = 10
        self._canvas.create_oval(
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
            fill=fill,
            outline=outline,
            width=1,
        )

    def _draw_check(self, cx: int, cy: int) -> None:
        canvas = self._canvas
        canvas.create_line(
            cx - 5,
            cy,
            cx - 1,
            cy + 4,
            fill=SUCCESS,
            width=2.5,
            capstyle="round",
            joinstyle="round",
        )
        canvas.create_line(
            cx - 1,
            cy + 4,
            cx + 6,
            cy - 4,
            fill=SUCCESS,
            width=2.5,
            capstyle="round",
            joinstyle="round",
        )

    def _draw_cross(self, cx: int, cy: int) -> None:
        canvas = self._canvas
        canvas.create_line(
            cx - 4,
            cy - 4,
            cx + 4,
            cy + 4,
            fill=ERROR,
            width=2.5,
            capstyle="round",
        )
        canvas.create_line(
            cx - 4,
            cy + 4,
            cx + 4,
            cy - 4,
            fill=ERROR,
            width=2.5,
            capstyle="round",
        )

    def destroy(self) -> None:
        """Tear down the windows (called on quit)."""
        try:
            self._running = False
            self._ticking = False
            self._win.destroy()
            self.root.quit()
            self.root.destroy()
        except Exception:  # pragma: no cover - defensive
            pass


def _rounded_rect_points(
    x1: int, y1: int, x2: int, y2: int, radius: int, steps: int = 10
) -> list[float]:
    """Point list tracing quarter-circle corners, for a crisp pill shape."""
    r = max(0, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    corners = (
        (x1 + r, y1 + r, 180, 270),  # top-left
        (x2 - r, y1 + r, 270, 360),  # top-right
        (x2 - r, y2 - r, 0, 90),  # bottom-right
        (x1 + r, y2 - r, 90, 180),  # bottom-left
    )
    points: list[float] = []
    for cx, cy, start, end in corners:
        for index in range(steps + 1):
            angle = math.radians(start + (end - start) * index / steps)
            points.extend((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def _fit_text(text: str, max_width: int, font: tkfont.Font) -> str:
    """Trim *text* with an ellipsis until it fits *max_width* pixels."""
    if font.measure(text) <= max_width:
        return text
    ellipsis = "…"
    ellipsis_width = font.measure(ellipsis)
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if font.measure(text[:middle]) + ellipsis_width <= max_width:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + ellipsis


def _blend(color_a: str, color_b: str, amount: float) -> str:
    """Blend two ``#rrggbb`` colours by *amount* (0 = a, 1 = b)."""
    amount = max(0.0, min(1.0, amount))
    a = tuple(int(color_a[index : index + 2], 16) for index in (1, 3, 5))
    b = tuple(int(color_b[index : index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(
        f"{round(channel_a + (channel_b - channel_a) * amount):02x}"
        for channel_a, channel_b in zip(a, b, strict=False)
    )
