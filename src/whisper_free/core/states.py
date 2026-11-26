"""Application state machine definitions.

The controller moves through these states as the user interacts with the
application.  The overlay and system tray reflect the current state.
"""

from __future__ import annotations

from enum import Enum, auto


class AppState(Enum):
    """Lifecycle states of the transcription assistant."""

    IDLE = auto()
    """Waiting for the hotkey. Models stay warm until the idle timeout."""

    LISTENING = auto()
    """Capturing microphone audio (push-to-talk held or toggle active)."""

    PROCESSING = auto()
    """Running whisper + grammar correction on the captured audio."""

    INJECTING = auto()
    """Typing/pasting the final text into the focused window."""

    DISABLED = auto()
    """Assistant turned off by the user (hotkeys ignored)."""

    def is_busy(self) -> bool:
        return self in (AppState.LISTENING, AppState.PROCESSING, AppState.INJECTING)


class StateTransitionError(RuntimeError):
    """Raised when an invalid state transition is requested."""


# Allowed transitions — anything not listed here is a programming error.
_ALLOWED: dict[AppState, set[AppState]] = {
    AppState.IDLE: {AppState.LISTENING, AppState.DISABLED, AppState.IDLE},
    AppState.LISTENING: {AppState.PROCESSING, AppState.IDLE, AppState.DISABLED},
    AppState.PROCESSING: {AppState.INJECTING, AppState.IDLE, AppState.DISABLED},
    AppState.INJECTING: {AppState.IDLE, AppState.DISABLED},
    AppState.DISABLED: {AppState.IDLE},
}


def can_transition(current: AppState, new: AppState) -> bool:
    """Return True when moving from ``current`` to ``new`` is legal."""
    return new in _ALLOWED.get(current, set())


def assert_transition(current: AppState, new: AppState) -> None:
    """Raise :class:`StateTransitionError` for illegal transitions."""
    if not can_transition(current, new):
        raise StateTransitionError(f"Illegal transition: {current.name} -> {new.name}")
