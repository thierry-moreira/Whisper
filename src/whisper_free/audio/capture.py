"""Microphone capture built on sounddevice/PortAudio.

The stream runs with a low-latency callback; chunks are forwarded to a
consumer (typically the :class:`~whisper_free.audio.buffer.AudioBuffer`).
Importing sounddevice is deferred so unit tests can run without the library.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import numpy as np

from whisper_free.config.settings import AudioSettings
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.audio.capture")

AudioCallback = Callable[[np.ndarray], None]


class AudioCaptureError(RuntimeError):
    """Raised when the microphone stream cannot start/stop."""


class AudioCapture:
    """Wraps a sounddevice.InputStream with start/stop semantics."""

    def __init__(self, settings: AudioSettings) -> None:
        self._settings = settings
        self._stream: Any | None = None
        self._callback: AudioCallback | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ API
    def start(self, callback: AudioCallback) -> None:
        """Open the microphone and forward chunks to ``callback``."""
        with self._lock:
            if self._stream is not None:
                logger.debug("Capture already running — ignoring start()")
                return
            self._callback = callback
            try:
                import sounddevice as sd
            except Exception as exc:  # pragma: no cover - env dependent
                raise AudioCaptureError(f"sounddevice unavailable: {exc}") from exc

            device = self._resolve_device(sd)
            try:
                self._stream = sd.InputStream(
                    samplerate=self._settings.sample_rate,
                    channels=self._settings.channels,
                    dtype="int16",
                    blocksize=self._settings.blocksize,
                    device=device,
                    callback=self._on_audio,
                    latency="low",
                )
                self._stream.start()
            except Exception as exc:
                self._stream = None
                raise AudioCaptureError(f"Failed to start microphone: {exc}") from exc
            logger.info(
                "Microphone capture started (device={}, sr={}Hz, block={})",
                device or "default",
                self._settings.sample_rate,
                self._settings.blocksize,
            )

    def stop(self) -> None:
        """Stop and close the stream. Safe to call when not running."""
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
            logger.info("Microphone capture stopped")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Error while stopping capture: {exc}")

    # ----------------------------------------------------------- properties
    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._stream is not None

    # -------------------------------------------------------------- callback
    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:  # overflows etc. — log but keep going
            logger.warning(f"Audio stream status: {status}")
        callback = self._callback
        if callback is None:
            return
        try:
            callback(indata)
        except Exception as exc:  # pragma: no cover - never kill the audio thread
            logger.error(f"Audio callback raised: {exc}")

    # --------------------------------------------------------------- helpers
    def _resolve_device(self, sd_module) -> str | int | None:
        """Resolve the configured device (index, name substring or default)."""
        raw = (self._settings.device or "").strip()
        if not raw:
            return None
        if raw.isdigit():
            return int(raw)
        try:
            devices = sd_module.query_devices()
            for idx, dev in enumerate(devices):
                name_matches = raw.lower() in str(dev.get("name", "")).lower()
                if name_matches and int(dev.get("max_input_channels", 0)) > 0:
                    logger.info(f"Using input device #{idx}: {dev.get('name')}")
                    return idx
        except Exception as exc:
            logger.warning(f"Could not enumerate audio devices: {exc}")
        logger.warning(f"Input device '{raw}' not found — using system default")
        return None

    @staticmethod
    def list_input_devices() -> list[dict]:
        """Return available input-capable devices (for the settings UI)."""
        try:
            import sounddevice as sd

            return [
                {"index": i, "name": d.get("name", ""), "channels": d.get("max_input_channels", 0)}
                for i, d in enumerate(sd.query_devices())
                if int(d.get("max_input_channels", 0)) > 0
            ]
        except Exception as exc:
            logger.warning(f"Device enumeration failed: {exc}")
            return []
