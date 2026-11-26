"""Thread-safe audio accumulator.

Chunks arrive from the sounddevice callback thread while the controller may
read/consume them from another thread.  The buffer stores numpy arrays and
can concatenate them into a single mono signal for whisper.
"""

from __future__ import annotations

import threading

import numpy as np

from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.audio.buffer")


class AudioBuffer:
    """Accumulates audio chunks in a thread-safe way."""

    def __init__(self, sample_rate: int = 16_000) -> None:
        self._sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._total_samples = 0

    # ------------------------------------------------------------------ API
    def append(self, chunk: np.ndarray) -> None:
        """Add a chunk (copied defensively — sounddevice reuses its buffer)."""
        if chunk is None or chunk.size == 0:
            return
        with self._lock:
            self._chunks.append(np.array(chunk, copy=True))
            self._total_samples += int(chunk.shape[0])

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._total_samples = 0

    def get_audio(self) -> np.ndarray:
        """Return all accumulated audio as one contiguous 1-D float32 array.

        The buffer contents are preserved (call :meth:`clear` to reset).
        Values are normalised to ``[-1.0, 1.0]`` when the input dtype is int16.
        Multi-channel input is down-mixed to mono.
        """
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            stacked = np.concatenate(self._chunks, axis=0)
        # Normalise int16 first, then down-mix to mono in float32 space
        if stacked.dtype == np.int16:
            stacked = stacked.astype(np.float32) / 32768.0
        return self._to_float32(self.flatten_channels(stacked))

    def consume(self) -> np.ndarray:
        """Return the audio (1-D float32 mono) and reset the buffer atomically."""
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            stacked = np.concatenate(self._chunks, axis=0)
            self._chunks.clear()
            self._total_samples = 0
        # Normalise int16 first, then down-mix to mono in float32 space
        if stacked.dtype == np.int16:
            stacked = stacked.astype(np.float32) / 32768.0
        return self._to_float32(self.flatten_channels(stacked))

    # ------------------------------------------------------------ properties
    @property
    def duration_s(self) -> float:
        with self._lock:
            return self._total_samples / self._sample_rate

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return self._total_samples == 0

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _to_float32(samples: np.ndarray) -> np.ndarray:
        """Normalise common PCM dtypes to float32 in [-1, 1]."""
        if samples.dtype == np.int16:
            return samples.astype(np.float32) / 32768.0
        if samples.dtype == np.int32:
            return samples.astype(np.float32) / 2147483648.0
        if samples.dtype == np.float32:
            return np.clip(samples, -1.0, 1.0)
        return samples.astype(np.float32)

    @staticmethod
    def flatten_channels(samples: np.ndarray) -> np.ndarray:
        """Down-mix a multi-channel signal (N, C) to mono (N,)."""
        if samples.ndim == 2 and samples.shape[1] > 1:
            return samples.mean(axis=1)
        if samples.ndim == 2 and samples.shape[1] == 1:
            return samples[:, 0]
        return samples
