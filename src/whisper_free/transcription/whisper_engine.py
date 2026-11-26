"""Whisper transcription engine (faster-whisper / CTranslate2).

The heavy ``faster_whisper`` import happens only inside
:func:`create_whisper_model` so that the rest of the codebase (and the unit
tests) never needs the library installed.
"""

from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from whisper_free.config.settings import Settings
from whisper_free.transcription.cuda_runtime import register_nvidia_dlls
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.stt")


@dataclass
class TranscriptionResult:
    """Outcome of a single transcription pass."""

    text: str = ""
    language: str = ""
    language_probability: float = 0.0
    duration_s: float = 0.0
    elapsed_s: float = 0.0
    segments: list[dict] = field(default_factory=list)

    @property
    def realtime_factor(self) -> float:
        """audio seconds processed per wall-clock second (>1 is faster than realtime)."""
        if self.elapsed_s <= 0:
            return 0.0
        return self.duration_s / self.elapsed_s


_CUDA_ERROR_MARKERS = ("cuda", "cudnn", "cublas", "cublaslt", "nvidia", "gpu")
_CUDA_DLLS = ("cublas64_12.dll", "cudnn64_9.dll")


def _is_cuda_failure(exc: Exception) -> bool:
    """Heuristic: did the failure come from the CUDA backend?"""
    message = str(exc).lower()
    return any(marker in message for marker in _CUDA_ERROR_MARKERS)


def _cuda_runtime_available() -> bool:
    """Check that CTranslate2's CUDA runtime DLLs can actually be loaded.

    ``ctranslate2.get_cuda_device_count()`` only needs the NVIDIA driver, so
    it can report a GPU even when cuBLAS is missing.  CTranslate2 loads the
    CUDA libraries lazily: the model builds fine and only the first encode
    fails (or hangs).  Probing the DLL up front lets the factory choose the
    CPU before the user starts dictating.
    """
    if sys.platform != "win32":
        return True
    register_nvidia_dlls()
    for dll in _CUDA_DLLS:
        try:
            ctypes.WinDLL(dll)
        except OSError as exc:
            logger.warning(f"CUDA runtime unavailable ({dll}: {exc})")
            return False
    return True


def _resolve_compute_type(device: str, requested: str) -> str:
    if requested == "auto":
        return "int8_float16" if device == "cuda" else "int8"
    if device == "cpu" and requested in ("int8_float16", "float16"):
        logger.warning(f"compute_type '{requested}' not supported on CPU — using int8")
        return "int8"
    return requested


def _build_model(model_cls: Any, whisper: Any, device: str, compute_type: str) -> Any:
    logger.info(f"Creating WhisperModel({whisper.model_size}, {device}, {compute_type})")
    return model_cls(
        whisper.model_size,
        device=device,
        compute_type=compute_type,
        cpu_threads=whisper.cpu_threads,
        download_root=whisper.model_dir,
    )


def create_whisper_model(settings: Settings, *, force_cpu: bool = False) -> Any:
    """Instantiate a ``faster_whisper.WhisperModel`` from settings.

    When CUDA cannot be initialised (missing cuBLAS/cuDNN, driver mismatch,
    unsupported GPU) and ``whisper.fallback_to_cpu`` is enabled, the model is
    rebuilt on the CPU with ``int8`` so dictation keeps working instead of
    failing outright.
    """
    from faster_whisper import WhisperModel  # deferred heavy import

    whisper = settings.whisper
    if force_cpu:
        device = "cpu"
    else:
        device = whisper.device
        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"
        if device == "cuda" and not _cuda_runtime_available():
            if not whisper.fallback_to_cpu:
                raise RuntimeError(
                    "CUDA runtime libraries are missing and whisper.fallback_to_cpu is disabled"
                )
            logger.warning(
                "CUDA runtime libraries are missing — falling back to CPU/int8. "
                "Install the CUDA 12 runtime (cuBLAS) to use the GPU."
            )
            device = "cpu"

    compute_type = _resolve_compute_type(device, whisper.compute_type)
    try:
        model = _build_model(WhisperModel, whisper, device, compute_type)
    except Exception as exc:
        if device != "cuda" or not whisper.fallback_to_cpu or not _is_cuda_failure(exc):
            raise
        logger.warning(
            f"CUDA initialisation failed ({exc}). Falling back to CPU/int8 — "
            "transcription will be slower."
        )
        model = _build_model(WhisperModel, whisper, "cpu", "int8")
        device = "cpu"
    # faster_whisper does not expose the effective device; GPUManager reads it
    # for stats/logs, so record the device that was actually built.
    model.device = device
    return model


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class WhisperEngine:
    """Transcribes float32 mono audio using a (lazily loaded) whisper model."""

    def __init__(self, settings: Settings, gpu_manager: Any) -> None:
        self._settings = settings
        self._gpu = gpu_manager

    # ------------------------------------------------------------------ API
    def transcribe(self, audio: np.ndarray) -> TranscriptionResult:
        """Transcribe a mono float32 signal sampled at 16 kHz (range [-1, 1])."""
        if audio is None or audio.size == 0:
            logger.warning("Empty audio received — skipping transcription")
            return TranscriptionResult()

        self._gpu.ensure_loaded(need_whisper=True)
        model = self._gpu.whisper
        if model is None:  # pragma: no cover - defensive
            raise RuntimeError("Whisper model unavailable after ensure_loaded()")

        whisper = self._settings.whisper
        language = whisper.language or None

        started = time.perf_counter()
        try:
            segments, info = self._run(model, audio)
        except Exception as exc:
            if not self._can_retry_on_cpu(model, exc):
                raise
            logger.warning(
                f"CUDA transcription failed ({exc}). Retrying on CPU/int8 — "
                "transcription will be slower."
            )
            model = self._gpu.switch_to_cpu()
            segments, info = self._run(model, audio)
        elapsed = time.perf_counter() - started

        text = " ".join(seg["text"].strip() for seg in segments).strip()
        result = TranscriptionResult(
            text=text,
            language=getattr(info, "language", language or ""),
            language_probability=float(getattr(info, "language_probability", 0.0)),
            duration_s=float(getattr(info, "duration", audio.size / 16_000)),
            elapsed_s=elapsed,
            segments=segments,
        )
        logger.info(
            "Transcribed {:.2f}s audio in {:.2f}s (x{:.1f} realtime): '{}'",
            result.duration_s,
            elapsed,
            result.realtime_factor,
            _preview(text),
        )
        return result

    def warmup(self) -> None:
        """Load the model and run 0.5s of silence through it (reduces first-use latency)."""
        try:
            self._gpu.ensure_loaded(need_whisper=True)
            silence = np.zeros(8_000, dtype=np.float32)
            model = self._gpu.whisper
            if model is not None:
                list(
                    model.transcribe(
                        silence,
                        language=self._settings.whisper.language or None,
                        beam_size=1,
                        vad_filter=False,
                    )[0]
                )
            logger.info("Whisper warmup complete")
        except Exception as exc:  # pragma: no cover - warmup must never crash startup
            logger.warning(f"Warmup failed (non fatal): {exc}")

    # -------------------------------------------------------------- internal
    def _run(self, model: Any, audio: np.ndarray) -> tuple[list[dict], Any]:
        """Run one transcription pass and materialise the lazy segment iterator."""
        whisper = self._settings.whisper
        segments_iter, info = model.transcribe(
            audio,
            language=whisper.language or None,
            beam_size=whisper.beam_size,
            vad_filter=whisper.vad_filter,
            vad_parameters={
                "threshold": 0.5,
                "min_speech_duration_ms": 250,
                "max_speech_duration_s": 30,
                "min_silence_duration_ms": 400,
            },
            condition_on_previous_text=whisper.condition_on_previous_text,
            word_timestamps=False,
        )
        segments = [
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text,
            }
            for seg in segments_iter
        ]
        return segments, info

    def _can_retry_on_cpu(self, model: Any, exc: Exception) -> bool:
        if not self._settings.whisper.fallback_to_cpu:
            return False
        if str(getattr(model, "device", "")).lower() != "cuda":
            return False
        return _is_cuda_failure(exc)


def _preview(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
