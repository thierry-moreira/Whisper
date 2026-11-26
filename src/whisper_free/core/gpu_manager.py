"""GPU lifecycle manager — lazy loading, idle unload and VRAM release.

The model is loaded on the first transcription and kept warm between
dictations so the next sentence does not pay the ~3 s reload cost.  After
``whisper.idle_unload_seconds`` without use (60 s by default), the model is
dropped and the CUDA cache is emptied when ``torch`` is available.

The manager is thread-safe: all public methods may be called from the audio
thread, the hotkey thread or the processing worker.
"""

from __future__ import annotations

import gc
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from whisper_free.config.settings import Settings
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.gpu")


@dataclass
class GPUStats:
    """Snapshot of the manager's current allocation state."""

    loaded: bool = False
    device: str = "unknown"
    load_time_s: float = 0.0
    whisper_model: str = ""
    grammar_ready: bool = False


@dataclass
class _Factories:
    """Callables that create the heavy objects on demand (injected for tests)."""

    whisper_factory: Callable[[], Any] | None = None
    whisper_cpu_factory: Callable[[], Any] | None = None
    grammar_factory: Callable[[], Any] | None = None
    torch_module: Any = field(default=None)


class GPUManager:
    """Owns the lifetime of GPU-resident models (whisper / grammar)."""

    def __init__(self, settings: Settings, factories: _Factories | None = None) -> None:
        self._settings = settings
        self._factories = factories or _Factories()
        self._lock = threading.RLock()
        self._whisper: Any | None = None
        self._grammar: Any | None = None
        self._stats = GPUStats()
        self._active_uses = 0
        self._idle_timer: threading.Timer | None = None
        self._last_used = 0.0
        self._pending_unload = False

    # ------------------------------------------------------------------ load
    def ensure_loaded(self, need_whisper: bool = True, need_grammar: bool = False) -> None:
        """Load the requested models if they are not yet resident."""
        with self._lock:
            if need_whisper and self._whisper is None:
                self._load_whisper()
            if need_grammar and self._grammar is None:
                self._load_grammar()
            self._last_used = time.monotonic()

    def begin_use(self) -> None:
        """Mark the start of a transcription so idle unload cannot race it."""
        with self._lock:
            self._active_uses += 1
            self._cancel_idle_timer_locked()

    def end_use(self) -> None:
        """Mark the end of a transcription and schedule the idle unload."""
        unload_now = False
        with self._lock:
            if self._active_uses > 0:
                self._active_uses -= 1
            self._last_used = time.monotonic()
            if self._active_uses == 0:
                if self._pending_unload or self._settings.whisper.unload_after_use:
                    self._pending_unload = False
                    unload_now = True
                else:
                    self._schedule_idle_unload_locked()
        if unload_now:
            self.unload_models()

    def touch(self) -> None:
        """Refresh the idle clock after an explicit warm-up."""
        with self._lock:
            self._last_used = time.monotonic()
            if self._active_uses == 0:
                self._schedule_idle_unload_locked()

    def _load_whisper(self) -> None:
        factory = self._factories.whisper_factory or self._default_whisper_factory
        started = time.perf_counter()
        logger.info(
            "Loading whisper model '{}' (device={}, compute={})...",
            self._settings.whisper.model_size,
            self._settings.whisper.device,
            self._settings.whisper.compute_type,
        )
        self._whisper = factory()
        elapsed = time.perf_counter() - started
        self._stats.loaded = True
        self._stats.load_time_s = elapsed
        self._stats.whisper_model = self._settings.whisper.model_size
        self._stats.device = str(getattr(self._whisper, "device", self._settings.whisper.device))
        self._last_used = time.monotonic()
        logger.info("Whisper model loaded in {:.2f}s (device={})", elapsed, self._stats.device)

    def _load_grammar(self) -> None:
        factory = self._factories.grammar_factory
        if factory is None:
            logger.warning("Grammar factory not configured; skipping grammar load")
            return
        started = time.perf_counter()
        logger.info("Starting grammar engine ({})...", self._settings.grammar.language)
        self._grammar = factory()
        self._stats.grammar_ready = True
        logger.info("Grammar engine ready in {:.2f}s", time.perf_counter() - started)

    def _default_whisper_factory(self) -> Any:
        from whisper_free.transcription.whisper_engine import create_whisper_model

        return create_whisper_model(self._settings)

    def _default_cpu_whisper_factory(self) -> Any:
        from whisper_free.transcription.whisper_engine import create_whisper_model

        return create_whisper_model(self._settings, force_cpu=True)

    def switch_to_cpu(self) -> Any:
        """Rebuild the whisper model on CPU after a runtime CUDA failure."""
        with self._lock:
            factory = self._factories.whisper_cpu_factory or self._default_cpu_whisper_factory
            started = time.perf_counter()
            logger.warning("Rebuilding whisper model on CPU after CUDA failure...")
            self._whisper = None
            gc.collect()
            self._whisper = factory()
            elapsed = time.perf_counter() - started
            self._stats.loaded = True
            self._stats.load_time_s = elapsed
            self._stats.whisper_model = self._settings.whisper.model_size
            self._stats.device = str(getattr(self._whisper, "device", "cpu"))
            self._last_used = time.monotonic()
            logger.info("Whisper model rebuilt on CPU in {:.2f}s", elapsed)
            return self._whisper

    # ---------------------------------------------------------------- access
    @property
    def whisper(self) -> Any | None:
        return self._whisper

    @property
    def grammar(self) -> Any | None:
        return self._grammar

    @property
    def stats(self) -> GPUStats:
        with self._lock:
            return GPUStats(**vars(self._stats))

    # -------------------------------------------------------------- unload
    def unload_models(self, *, force: bool = False) -> None:
        """Drop model references and free VRAM as aggressively as possible.

        When a transcription is in flight the unload is deferred until
        :meth:`end_use` runs, unless ``force=True`` (shutdown).
        """
        with self._lock:
            self._cancel_idle_timer_locked()
            if self._active_uses > 0 and not force:
                self._pending_unload = True
                logger.debug("Unload deferred while a transcription is in flight")
                return
            if self._whisper is None and self._grammar is None:
                return
            logger.debug("Unloading models and releasing VRAM...")
            self._whisper = None
            self._grammar = None
            self._stats.loaded = False
            self._stats.grammar_ready = False
            self._stats.whisper_model = ""
            self._stats.device = "unknown"
        gc.collect()
        self._empty_cuda_cache()

    # --------------------------------------------------------- idle handling
    def _schedule_idle_unload_locked(self) -> None:
        self._cancel_idle_timer_locked()
        delay = self._settings.whisper.idle_unload_seconds
        if delay <= 0 or (self._whisper is None and self._grammar is None):
            return
        timer = threading.Timer(delay, self._idle_unload)
        timer.daemon = True
        self._idle_timer = timer
        timer.start()

    def _cancel_idle_timer_locked(self) -> None:
        timer, self._idle_timer = self._idle_timer, None
        if timer is not None:
            timer.cancel()

    def _idle_unload(self) -> None:
        """Timer callback: unload only if the model is still idle."""
        with self._lock:
            self._idle_timer = None
            if self._active_uses > 0:
                return
            delay = self._settings.whisper.idle_unload_seconds
            remaining = delay - (time.monotonic() - self._last_used)
            if remaining > 0.05:
                timer = threading.Timer(remaining, self._idle_unload)
                timer.daemon = True
                self._idle_timer = timer
                timer.start()
                return
        logger.info("Idle timeout reached — unloading model from VRAM")
        self.unload_models()

    def _empty_cuda_cache(self) -> None:
        torch_module = self._factories.torch_module
        if torch_module is None:
            try:  # optional dependency
                import torch as torch_module  # type: ignore[no-redef]
            except Exception:
                logger.debug("torch not installed — skipping CUDA cache cleanup")
                return
        try:
            if torch_module.cuda.is_available():
                torch_module.cuda.empty_cache()
                logger.debug("torch.cuda.empty_cache() executed")
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"CUDA cache cleanup failed: {exc}")

    # --------------------------------------------------------------- status
    @staticmethod
    def cuda_available() -> bool:
        """Best-effort CUDA availability probe (without importing torch)."""
        try:
            import ctranslate2

            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            return False
