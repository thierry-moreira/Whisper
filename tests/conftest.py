"""Shared fixtures and test doubles.

The fakes below implement the same minimal surface the real components
expose, so the controller and pipeline can be exercised without a GPU,
microphone, keyboard hooks or a Tk display.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# Make ``src/`` importable when running pytest without installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whisper_free.config.settings import Settings  # noqa: E402
from whisper_free.input.injector import InjectResult  # noqa: E402
from whisper_free.transcription.grammar import GrammarResult  # noqa: E402
from whisper_free.transcription.pipeline import PipelineResult, TranscriptionMode  # noqa: E402
from whisper_free.transcription.whisper_engine import TranscriptionResult  # noqa: E402

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Deterministic settings for tests — no real device, no grammar server."""
    s = Settings()
    s.whisper.model_size = "tiny"
    s.whisper.device = "cpu"
    s.whisper.compute_type = "int8"
    s.whisper.model_dir = str(tmp_path / "models")
    s.grammar.enabled = False
    s.audio.device = ""
    s.overlay.enabled = True
    s.injector.pre_inject_delay_s = 0.0
    s.hotkey.suppress = False
    return s


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------


@pytest.fixture
def audio_chunk() -> np.ndarray:
    """1 s of int16 mono audio (440 Hz tone) shaped like a sounddevice chunk."""
    t = np.linspace(0, 1.0, 16_000, endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * 440 * t) * 32_767).astype(np.int16)
    return tone.reshape(-1, 1)


@pytest.fixture
def float_audio() -> np.ndarray:
    """0.5 s of float32 mono audio in [-1, 1]."""
    t = np.linspace(0, 0.5, 8_000, endpoint=False)
    return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


# ---------------------------------------------------------------------------
# Fake components
# ---------------------------------------------------------------------------


class FakeAudioCapture:
    """Records start/stop calls and forwards chunks on demand."""

    def __init__(self) -> None:
        self.started = False
        self.callback = None
        self.start_calls = 0
        self.stop_calls = 0
        self.raise_on_start: Exception | None = None

    def start(self, callback) -> None:
        if self.raise_on_start is not None:
            raise self.raise_on_start
        self.started = True
        self.callback = callback
        self.start_calls += 1

    def stop(self) -> None:
        self.started = False
        self.callback = None
        self.stop_calls += 1

    @property
    def is_running(self) -> bool:
        return self.started

    def push(self, chunk: np.ndarray) -> None:
        if self.callback is not None:
            self.callback(chunk)


class FakeInjector:
    """Captures injected text; optional failure injection."""

    def __init__(self, success: bool = True, error: str | None = None) -> None:
        self.injected: list[str] = []
        self.success = success
        self.error = error

    def inject(self, text: str) -> InjectResult:
        self.injected.append(text)
        return InjectResult(text=text, method="fake", success=self.success, error=self.error)


class FakePipeline:
    """Returns a canned pipeline result."""

    def __init__(self, final_text: str = "Olá mundo.", error: str | None = None) -> None:
        self.final_text = final_text
        self.error = error
        self.processed: list[np.ndarray] = []
        self.modes: list[TranscriptionMode] = []
        self.release_calls = 0
        self.shutdown_calls = 0
        self.prepare_calls = 0
        self.warmup_calls = 0

    def process(
        self, audio: np.ndarray, mode: TranscriptionMode = TranscriptionMode.LOCAL
    ) -> PipelineResult:
        self.processed.append(audio)
        self.modes.append(mode)
        return PipelineResult(
            final_text="" if self.error else self.final_text,
            transcription=TranscriptionResult(text=self.final_text or "", language="pt"),
            grammar=GrammarResult(corrected=self.final_text or ""),
            mode=mode,
            total_elapsed_s=0.01,
            error=self.error,
        )

    def release_gpu(self) -> None:
        self.release_calls += 1

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def prepare_grammar(self) -> None:
        self.prepare_calls += 1

    def warmup(self) -> None:
        self.warmup_calls += 1


class FakeOverlay:
    """Records overlay method calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.cloud_calls: list[tuple[str, bool]] = []
        self.openai_dialog: dict[str, Any] | None = None
        self.stopped = False

    def show_listening(self, cloud: bool = False) -> None:
        self.calls.append(("listening", ""))
        self.cloud_calls.append(("listening", cloud))

    def show_processing(self, cloud: bool = False) -> None:
        self.calls.append(("processing", ""))
        self.cloud_calls.append(("processing", cloud))

    def show_success(self, text: str) -> None:
        self.calls.append(("success", text))

    def show_error(self, message: str) -> None:
        self.calls.append(("error", message))

    def hide(self) -> None:
        self.calls.append(("hide", ""))

    def show_openai_settings(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        on_save,
    ) -> None:
        self.openai_dialog = {
            "api_key": api_key,
            "model": model,
            "base_url": base_url,
            "on_save": on_save,
        }

    def stop(self) -> None:
        self.stopped = True

    def run(self) -> None:  # pragma: no cover - never called in tests
        pass

    def states(self) -> list[str]:
        return [name for name, _ in self.calls]


class FakeTray:
    """Records tray interactions."""

    def __init__(self) -> None:
        self.refreshes = 0
        self.notifications: list[str] = []
        self.stopped = False

    def refresh(self) -> None:
        self.refreshes += 1

    def notify(self, message: str, title: str = "") -> None:
        self.notifications.append(message)

    def stop(self) -> None:
        self.stopped = True

    def start(self) -> None:
        pass


class FakeStartup:
    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self.set_calls: list[bool] = []

    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> bool:
        self._enabled = True
        self.set_calls.append(True)
        return True

    def disable(self) -> bool:
        self._enabled = False
        self.set_calls.append(False)
        return True

    def set_enabled(self, value: bool) -> bool:
        return self.enable() if value else self.disable()


class InlineExecutor:
    """Executes submitted jobs synchronously (deterministic tests)."""

    def __init__(self) -> None:
        self.jobs: list[tuple[Any, tuple]] = []
        self.run_immediately = True

    def submit(self, fn, *args, **kwargs):
        self.jobs.append((fn, args))
        if self.run_immediately:
            fn(*args, **kwargs)
        return None

    def shutdown(self, **kwargs) -> None:
        pass

    def run_pending(self) -> None:
        for fn, args in self.jobs:
            fn(*args)
        self.jobs.clear()


class FakeHotkeyBackend:
    """Minimal keyboard-module stand-in.

    Like the real ``keyboard`` library, ``add_hotkey`` returns a remover
    callable and ``remove_hotkey`` accepts that same callable.
    """

    def __init__(self) -> None:
        self.registered: list[tuple[str, dict]] = []
        self.removed: list = []
        self._next_handle = 1

    def add_hotkey(self, hotkey: str, callback, **kwargs):
        handle_id = self._next_handle
        self._next_handle += 1

        def remove() -> None:
            self.removed.append(remove)

        remove.handle_id = handle_id  # type: ignore[attr-defined]
        self.registered.append((hotkey, {"callback": callback, **kwargs}))
        return remove

    def remove_hotkey(self, handle) -> None:
        self.removed.append(handle)

    def get_callback(self, index: int):
        """Extract callback from registered entry (handles tuple format)."""
        entry = self.registered[index]
        if isinstance(entry, tuple) and len(entry) == 2:
            return entry[1].get("callback")
        return None


# ---------------------------------------------------------------------------
# Fixtures wiring the fakes
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_capture() -> FakeAudioCapture:
    return FakeAudioCapture()


@pytest.fixture
def fake_injector() -> FakeInjector:
    return FakeInjector()


@pytest.fixture
def fake_pipeline() -> FakePipeline:
    return FakePipeline()


@pytest.fixture
def fake_overlay() -> FakeOverlay:
    return FakeOverlay()


@pytest.fixture
def fake_tray() -> FakeTray:
    return FakeTray()


@pytest.fixture
def fake_startup() -> FakeStartup:
    return FakeStartup()


@pytest.fixture
def inline_executor() -> InlineExecutor:
    ex = InlineExecutor()
    ex.run_immediately = False
    return ex


@pytest.fixture
def fake_hotkey_backend() -> FakeHotkeyBackend:
    return FakeHotkeyBackend()


@pytest.fixture
def controller(
    settings,
    fake_capture,
    fake_pipeline,
    fake_injector,
    fake_overlay,
    fake_tray,
    fake_startup,
    inline_executor,
):
    """A fully faked controller ready for behaviour testing."""
    from whisper_free.core.controller import Controller

    return Controller(
        settings,
        audio_capture=fake_capture,
        pipeline=fake_pipeline,
        injector=fake_injector,
        overlay=fake_overlay,
        tray=fake_tray,
        startup=fake_startup,
        executor=inline_executor,
    )
