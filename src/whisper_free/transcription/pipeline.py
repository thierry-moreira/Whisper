"""End-to-end transcription pipeline: audio → STT → grammar → text.

The pipeline is synchronous and designed to run inside a single worker thread
(see :class:`whisper_free.core.controller.Controller`).  It supports two
interchangeable speech-to-text backends:

* :attr:`TranscriptionMode.LOCAL` — faster-whisper on the GPU, loaded on demand
* :attr:`TranscriptionMode.CLOUD` — OpenAI ``/audio/transcriptions`` (WAV upload)

Both modes share the optional LanguageTool correction and the final
``cleanup_text`` normalisation.  The GPU is only touched in local mode.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from whisper_free.config.settings import Settings
from whisper_free.transcription.grammar import GrammarCorrector, GrammarResult, cleanup_text
from whisper_free.transcription.whisper_engine import TranscriptionResult, WhisperEngine
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.pipeline")


class TranscriptionMode(StrEnum):
    """Which backend should process the recording."""

    LOCAL = "local"
    CLOUD = "cloud"


@dataclass
class PipelineResult:
    """Everything produced by one pipeline run."""

    final_text: str = ""
    transcription: TranscriptionResult = field(default_factory=TranscriptionResult)
    grammar: GrammarResult = field(default_factory=GrammarResult)
    mode: TranscriptionMode = TranscriptionMode.LOCAL
    total_elapsed_s: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.final_text)


class TranscriptionPipeline:
    """Chains speech-to-text and grammar correction."""

    def __init__(
        self,
        settings: Settings,
        whisper_engine: WhisperEngine,
        grammar: GrammarCorrector,
        gpu_manager,
        openai_engine=None,
    ) -> None:
        self._settings = settings
        self._whisper = whisper_engine
        self._grammar = grammar
        self._gpu = gpu_manager
        self._openai = openai_engine

    # ------------------------------------------------------------------ API
    def process(
        self,
        audio: np.ndarray,
        mode: TranscriptionMode = TranscriptionMode.LOCAL,
    ) -> PipelineResult:
        """Run the full pipeline for a float32 mono signal (16 kHz)."""
        mode = mode if isinstance(mode, TranscriptionMode) else TranscriptionMode(mode)
        started = time.perf_counter()
        result = PipelineResult(mode=mode)
        use_gpu = mode is TranscriptionMode.LOCAL
        begin_use = getattr(self._gpu, "begin_use", None) if use_gpu else None
        end_use = getattr(self._gpu, "end_use", None) if use_gpu else None
        if begin_use is not None:
            begin_use()
        try:
            if use_gpu:
                transcription = self._whisper.transcribe(audio)
            else:
                if self._openai is None:
                    raise RuntimeError("OpenAI transcription engine is not configured")
                transcription = self._openai.transcribe(audio)
            result.transcription = transcription
            if not transcription.text:
                result.final_text = ""
                result.total_elapsed_s = time.perf_counter() - started
                return result

            grammar_result = self._grammar.correct(transcription.text)
            result.grammar = grammar_result
            result.final_text = cleanup_text(grammar_result.corrected or transcription.text)
        except Exception as exc:
            logger.exception(f"Pipeline failed ({mode.value})")
            result.error = str(exc)
        finally:
            if end_use is not None:
                end_use()
        result.total_elapsed_s = time.perf_counter() - started
        logger.info(
            "Pipeline ({}) finished in {:.2f}s -> '{}'",
            mode.value,
            result.total_elapsed_s,
            _preview(result.final_text),
        )
        return result

    def release_gpu(self) -> None:
        """Force an immediate unload (disable/shutdown, not every sentence).

        LanguageTool is intentionally kept running: it is a CPU-only Java
        server that idles at negligible cost, and restarting it takes several
        seconds (which would penalise the next transcription).
        """
        unload = getattr(self._gpu, "unload_models", None)
        if unload is not None:
            unload()

    def warmup(self) -> None:
        """Pre-load whisper for diagnostics (the normal flow loads on the hotkey)."""
        self._whisper.warmup()
        touch = getattr(self._gpu, "touch", None)
        if touch is not None:
            touch()

    def prepare_grammar(self) -> None:
        """Start and exercise LanguageTool so the first dictation is fast."""
        if self._settings.grammar.enabled:
            self._grammar.warmup()

    def shutdown(self) -> None:
        """Full cleanup on app exit: stop LanguageTool and free VRAM."""
        try:
            self._grammar.close()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Grammar close failed: {exc}")
        unload = getattr(self._gpu, "unload_models", None)
        if unload is not None:
            try:
                unload(force=True)
            except TypeError:  # fake/legacy manager without the flag
                unload()


def _preview(text: str, limit: int = 100) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
