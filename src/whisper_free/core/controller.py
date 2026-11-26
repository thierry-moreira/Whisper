"""Central orchestrator — wires every component and owns the state machine.

Threading model
---------------
* Hotkey callbacks arrive on the *keyboard listener* thread.
* Audio chunks arrive on the *sounddevice callback* thread.
* Transcription runs on a dedicated single-worker executor thread.
* UI updates are safe from any thread (the overlay marshals them internally).

Every state change is guarded by ``self._lock``.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from whisper_free.audio.buffer import AudioBuffer
from whisper_free.audio.capture import AudioCapture
from whisper_free.config import constants
from whisper_free.config.settings import Settings
from whisper_free.core.gpu_manager import GPUManager
from whisper_free.core.states import AppState, assert_transition, can_transition
from whisper_free.input.hotkey import HotkeyCallbacks, HotkeyManager
from whisper_free.input.injector import TextInjector
from whisper_free.startup.windows import WindowsStartup
from whisper_free.transcription.grammar import GrammarCorrector
from whisper_free.transcription.java_runtime import JavaRuntimeManager
from whisper_free.transcription.openai_engine import OpenAIEngine
from whisper_free.transcription.pipeline import (
    PipelineResult,
    TranscriptionMode,
    TranscriptionPipeline,
)
from whisper_free.transcription.whisper_engine import WhisperEngine
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.controller")


class Controller:
    """Coordinates audio capture, transcription, injection and the UI."""

    def __init__(
        self,
        settings: Settings,
        *,
        gpu_manager: Any | None = None,
        audio_capture: Any | None = None,
        pipeline: Any | None = None,
        injector: Any | None = None,
        hotkey: Any | None = None,
        overlay: Any | None = None,
        tray: Any | None = None,
        startup: Any | None = None,
        executor: Any | None = None,
        on_state_change: Callable[[AppState], None] | None = None,
    ) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._state = AppState.IDLE
        self._mode = TranscriptionMode.LOCAL
        self._enabled = True
        self._on_state_change = on_state_change
        self._max_timer: threading.Timer | None = None
        self._prepare_thread: threading.Thread | None = None
        # Incremented whenever a dictation starts and whenever the assistant is
        # enabled/disabled.  Workers capture it so a result produced after a
        # disable is discarded instead of injected.
        self._generation = 0

        self.gpu_manager = gpu_manager or GPUManager(settings)
        self.audio_buffer = AudioBuffer(sample_rate=settings.audio.sample_rate)

        grammar = GrammarCorrector(settings, JavaRuntimeManager())
        whisper_engine = WhisperEngine(settings, self.gpu_manager)
        openai_engine = OpenAIEngine(settings)
        self._pipeline_internal = TranscriptionPipeline(
            settings, whisper_engine, grammar, self.gpu_manager, openai_engine
        )
        self.pipeline = pipeline or self._pipeline_internal

        self.audio_capture = audio_capture or AudioCapture(settings.audio)
        self.injector = injector or TextInjector(settings.injector)
        self.startup = startup or WindowsStartup()
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="whisper-free-worker"
        )
        self.hotkey = hotkey or HotkeyManager(
            settings.hotkey,
            HotkeyCallbacks(
                on_press=self.on_hotkey_press,
                on_release=self.on_hotkey_release,
                on_toggle_enabled=self.toggle_enabled,
                on_cloud_press=self.on_cloud_hotkey_press,
                on_cloud_release=self.on_cloud_hotkey_release,
            ),
        )
        self.overlay = overlay  # created by main() (needs the Tk main thread)
        self.tray = tray

    # -------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Register hotkeys, sync auto-start entry and warm up in background."""
        self.hotkey.register()
        self._sync_autostart()
        self._prepare_thread = threading.Thread(
            target=self._prepare_async, name="whisper-free-prepare", daemon=True
        )
        self._prepare_thread.start()
        logger.info(
            "Controller started (hotkey='{}', cloud-hotkey='{}', mode='{}')",
            self.settings.hotkey.trigger,
            self.settings.hotkey.cloud_trigger,
            self.settings.hotkey.mode,
        )

    def shutdown(self) -> None:
        """Stop everything in the right order (idempotent)."""
        logger.info("Shutting down...")
        self._cancel_max_timer()
        try:
            if self.audio_capture.is_running:
                self.audio_capture.stop()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Audio stop failed: {exc}")
        try:
            self.hotkey.unregister()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Hotkey unregister failed: {exc}")
        try:
            self.pipeline.shutdown()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Pipeline shutdown failed: {exc}")
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(f"Tray stop failed: {exc}")
        try:
            if hasattr(self._executor, "shutdown"):
                self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:  # pragma: no cover - defensive
            pass
        logger.info("Shutdown complete")

    def _prepare_async(self) -> None:
        """Background warm-up: start LanguageTool so dictation is instant."""
        try:
            self.pipeline.prepare_grammar()
        except Exception as exc:  # pragma: no cover - must never crash startup
            logger.warning(f"Grammar pre-start failed (non fatal): {exc}")

    def _sync_autostart(self) -> None:
        """Apply the configured auto-start preference to the registry."""
        try:
            desired = self.settings.startup.auto_start
            current = self.startup.is_enabled()
            if desired != current:
                self.startup.set_enabled(desired)
                logger.info(f"Auto-start {'enabled' if desired else 'disabled'}")
        except Exception as exc:  # pragma: no cover - registry access issues
            logger.warning(f"Could not sync auto-start: {exc}")

    # ------------------------------------------------------------------ state
    @property
    def state(self) -> AppState:
        with self._lock:
            return self._state

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def _notify_state(self, new_state: AppState) -> None:
        callback = self._on_state_change
        if callback is None:
            return
        try:
            callback(new_state)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"State-change callback failed: {exc}")

    def _transition(self, new_state: AppState) -> None:
        with self._lock:
            if self._state == new_state:
                return
            assert_transition(self._state, new_state)
            self._state = new_state
            logger.debug(f"State: {new_state.name}")
        self._notify_state(new_state)

    def _try_transition(self, expected: AppState, new_state: AppState) -> bool:
        """Transition only when the current state is still ``expected``.

        The worker thread uses this instead of :meth:`_transition` so that a
        disable landing mid-transcription can never raise
        ``StateTransitionError`` nor inject into a disabled app.  Returns
        ``True`` when the transition happened.
        """
        with self._lock:
            if self._state != expected or not can_transition(self._state, new_state):
                return False
            self._state = new_state
            logger.debug(f"State: {new_state.name}")
        self._notify_state(new_state)
        return True

    def _is_current(self, generation: int) -> bool:
        """True when ``generation`` still belongs to the active dictation."""
        with self._lock:
            return self._enabled and self._generation == generation

    # ----------------------------------------------------------- hotkey events
    def on_hotkey_press(self) -> None:
        """Local (GPU) hotkey activated (keyboard listener thread)."""
        self._on_hotkey_press(TranscriptionMode.LOCAL)

    def on_hotkey_release(self) -> None:
        """Local (GPU) hotkey released (keyboard listener thread)."""
        self._on_hotkey_release(TranscriptionMode.LOCAL)

    def on_cloud_hotkey_press(self) -> None:
        """OpenAI API hotkey activated (keyboard listener thread)."""
        self._on_hotkey_press(TranscriptionMode.CLOUD)

    def on_cloud_hotkey_release(self) -> None:
        """OpenAI API hotkey released (keyboard listener thread)."""
        self._on_hotkey_release(TranscriptionMode.CLOUD)

    def _on_hotkey_press(self, mode: TranscriptionMode) -> None:
        if not self.enabled:
            logger.debug("Trigger ignored — assistant disabled")
            return
        if mode is TranscriptionMode.CLOUD and not self.is_openai_configured():
            logger.info("Cloud hotkey ignored — OpenAI API key is not configured")
            message = "Configure a chave da API OpenAI no menu do tray"
            self._show_error(message)
            if self.tray is not None:
                self.tray.notify(message)
            return
        with self._lock:
            if self._state != AppState.IDLE:
                logger.debug(f"Trigger ignored in state {self._state.name}")
                return
        self._start_listening(mode)

    def _on_hotkey_release(self, mode: TranscriptionMode) -> None:
        with self._lock:
            if self._state != AppState.LISTENING or self._mode is not mode:
                return
        self._stop_listening()

    # --------------------------------------------------------------- listening
    def _start_listening(self, mode: TranscriptionMode = TranscriptionMode.LOCAL) -> None:
        with self._lock:
            if not self._enabled or self._state != AppState.IDLE:
                return
            self._mode = mode
            self._generation += 1
        self.audio_buffer.clear()
        try:
            self.audio_capture.start(self._on_audio_chunk)
        except Exception as exc:
            logger.error(f"Microphone unavailable: {exc}")
            self._show_error("Microfone indisponível")
            return
        if not self._try_transition(AppState.IDLE, AppState.LISTENING):
            # Disabled between the guard above and the capture start.
            with contextlib.suppress(Exception):
                self.audio_capture.stop()
            return
        self._show_overlay("listening", mode=mode)
        self._arm_max_timer()

    def _stop_listening(self) -> None:
        self._cancel_max_timer()
        try:
            self.audio_capture.stop()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Audio stop failed: {exc}")

        with self._lock:
            state = self._state
            generation = self._generation
            mode = self._mode
        if state != AppState.LISTENING:
            # The assistant was disabled while the hotkey was held.
            return

        if self.audio_buffer.duration_s < constants.MIN_RECORDING_SECONDS:
            logger.debug("Recording too short — ignored")
            if self._try_transition(AppState.LISTENING, AppState.IDLE):
                self._show_overlay("hide")
            return

        audio = self.audio_buffer.consume()
        if not self._try_transition(AppState.LISTENING, AppState.PROCESSING):
            return
        self._show_overlay("processing", mode=mode)
        try:
            self._executor.submit(self._process_worker, audio, generation, mode)
        except Exception as exc:  # pragma: no cover - executor shut down
            logger.error(f"Could not schedule transcription: {exc}")
            self._try_transition(AppState.PROCESSING, AppState.IDLE)
            self._show_error("Falha ao agendar transcrição")

    def _on_audio_chunk(self, chunk) -> None:
        """sounddevice callback thread — keep it fast and allocation-light."""
        self.audio_buffer.append(chunk)

    def _arm_max_timer(self) -> None:
        self._cancel_max_timer()
        self._max_timer = threading.Timer(constants.MAX_RECORDING_SECONDS, self._auto_stop)
        self._max_timer.daemon = True
        self._max_timer.start()

    def _cancel_max_timer(self) -> None:
        timer, self._max_timer = self._max_timer, None
        if timer is not None:
            timer.cancel()

    def _auto_stop(self) -> None:
        logger.warning(f"Recording exceeded {constants.MAX_RECORDING_SECONDS}s — auto-stopping")
        with self._lock:
            if self._state != AppState.LISTENING:
                return
        self._stop_listening()

    # -------------------------------------------------------------- processing
    def _process_worker(
        self, audio, generation: int, mode: TranscriptionMode = TranscriptionMode.LOCAL
    ) -> None:
        """Runs on the executor thread: transcribe → correct → inject.

        ``generation`` identifies the dictation.  If the user disables the
        assistant (or starts a new one) while whisper is running, the result is
        discarded instead of injected.
        """
        try:
            result: PipelineResult = self.pipeline.process(audio, mode=mode)
        except Exception as exc:  # pragma: no cover - pipeline catches internally
            logger.exception("Unexpected pipeline crash")
            self._finish_with_error(str(exc), generation)
            return

        if not self._is_current(generation):
            logger.info("Dictation superseded while transcribing — result discarded")
            self._show_overlay("hide")
            return

        if result.error is not None:
            self._finish_with_error(result.error, generation)
            return

        if not result.final_text:
            logger.info("Nothing transcribed (silence or noise)")
            if self._try_transition(AppState.PROCESSING, AppState.IDLE):
                self._show_overlay("hide")
            return

        if not self._try_transition(AppState.PROCESSING, AppState.INJECTING):
            logger.info("Dictation superseded before injection — text discarded")
            self._show_overlay("hide")
            return

        inject_result = self.injector.inject(result.final_text)
        self._settle_after_injection()

        if inject_result.success:
            if self._is_current(generation):
                self._show_overlay("success", result.final_text)
        else:
            self._show_error(inject_result.error or "Falha ao digitar o texto")

    def _settle_after_injection(self) -> None:
        """Return to IDLE (or DISABLED if the user turned it off meanwhile)."""
        with self._lock:
            target = AppState.IDLE if self._enabled else AppState.DISABLED
            if self._state == target or not can_transition(self._state, target):
                return
            self._state = target
            logger.debug(f"State: {target.name}")
        self._notify_state(target)

    def _finish_with_error(self, message: str, generation: int | None = None) -> None:
        with self._lock:
            if generation is not None and generation != self._generation:
                logger.debug("Ignoring error from a superseded dictation")
                return
            target = AppState.IDLE if self._enabled else AppState.DISABLED
            changed = self._state != target and can_transition(self._state, target)
            if changed:
                self._state = target
                logger.debug(f"State: {target.name}")
        if changed:
            self._notify_state(target)
        self._show_error(message)

    # ------------------------------------------------------------- tray actions
    def toggle_enabled(self) -> None:
        """Enable/disable the assistant entirely (tray or toggle hotkey)."""
        with self._lock:
            self._enabled = not self._enabled
            enabled = self._enabled
            # Invalidate any dictation that is still being transcribed.
            self._generation += 1
            if not enabled and self._state == AppState.LISTENING:
                with contextlib.suppress(Exception):
                    self.audio_capture.stop()
                self._cancel_max_timer()
            target = AppState.IDLE if enabled else AppState.DISABLED
            changed = self._state != target and can_transition(self._state, target)
            if changed:
                self._state = target
                logger.debug(f"State: {target.name}")
            logger.info("Assistant %s", "ENABLED" if enabled else "DISABLED")
        if changed:
            self._notify_state(target)
        self._show_overlay("hide")
        if not enabled:
            with contextlib.suppress(Exception):
                self.pipeline.release_gpu()
        if self.tray is not None:
            self.tray.refresh()
            self.tray.notify("Assistente ativado" if enabled else "Assistente desativado")

    def toggle_overlay(self) -> None:
        """Show/hide the visual indicator (persistable via settings file)."""
        self.settings.overlay.enabled = not self.settings.overlay.enabled
        if not self.settings.overlay.enabled and self.overlay is not None:
            self._show_overlay("hide")
        if self.tray is not None:
            self.tray.refresh()
        logger.info(f"Overlay {'enabled' if self.settings.overlay.enabled else 'disabled'}")

    def is_overlay_enabled(self) -> bool:
        return bool(self.settings.overlay.enabled)

    def warmup(self) -> None:
        """Pre-load whisper into VRAM for diagnostics (normal flow loads on hotkey)."""
        if self.tray is not None:
            self.tray.notify("Carregando modelo Whisper… aguarde alguns segundos")
        try:
            self.pipeline.warmup()
            if self.tray is not None:
                self.tray.notify("Modelo carregado e pronto")
        except Exception as exc:
            logger.error(f"Warmup failed: {exc}")
            if self.tray is not None:
                self.tray.notify(f"Falha ao carregar modelo: {exc}")

    def is_autostart_enabled(self) -> bool:
        try:
            return self.startup.is_enabled()
        except Exception:  # pragma: no cover - registry issues
            return False

    def toggle_autostart(self) -> None:
        try:
            new_state = not self.startup.is_enabled()
            self.startup.set_enabled(new_state)
            self.settings.startup.auto_start = new_state
        except Exception as exc:
            logger.error(f"Auto-start toggle failed: {exc}")
        if self.tray is not None:
            self.tray.refresh()

    def is_openai_configured(self) -> bool:
        """True when the cloud hotkey has everything it needs."""
        config = self.settings.openai
        return bool(config.enabled and config.api_key.strip())

    def open_openai_settings(self) -> None:
        """Open the OpenAI key/model dialog, falling back to the .env file."""
        config = self.settings.openai
        if self.overlay is not None and hasattr(self.overlay, "show_openai_settings"):
            try:
                self.overlay.show_openai_settings(
                    api_key=config.api_key,
                    model=config.model,
                    base_url=config.base_url,
                    on_save=self._save_openai_settings,
                )
                return
            except Exception as exc:  # pragma: no cover - UI defensive
                logger.debug(f"OpenAI settings dialog failed: {exc}")
        logger.info("OpenAI settings dialog unavailable — opening .env")
        self.open_config()

    def _save_openai_settings(
        self,
        api_key: str,
        model: str,
        base_url: str,
        *,
        env_path: Path | None = None,
    ) -> str | None:
        """Validate and persist OpenAI settings; return an error message or None."""
        from pydantic import ValidationError

        from whisper_free.config.env_store import update_env_file
        from whisper_free.config.settings import OpenAISettings

        try:
            updated = OpenAISettings(
                enabled=self.settings.openai.enabled,
                api_key=api_key,
                model=model,
                base_url=base_url,
                language=self.settings.openai.language,
                prompt=self.settings.openai.prompt,
                timeout_seconds=self.settings.openai.timeout_seconds,
            )
        except ValidationError as exc:
            errors = exc.errors()
            return (
                str(errors[0].get("msg", "Configuração inválida"))
                if errors
                else "Configuração inválida"
            )

        path = env_path or constants.ENV_FILE
        try:
            if not path.exists() and constants.ENV_EXAMPLE_FILE.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    constants.ENV_EXAMPLE_FILE.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            update_env_file(
                path,
                {
                    "WHISPER_FREE_OPENAI__API_KEY": updated.api_key,
                    "WHISPER_FREE_OPENAI__MODEL": updated.model,
                    "WHISPER_FREE_OPENAI__BASE_URL": updated.base_url,
                },
            )
        except OSError as exc:
            logger.error(f"Could not save OpenAI settings: {exc}")
            return f"Não foi possível salvar o .env: {exc}"

        self.settings.openai = updated
        logger.info(
            "OpenAI settings saved (model='{}', key={})",
            updated.model,
            "configured" if updated.api_key else "empty",
        )
        if self.tray is not None:
            self.tray.refresh()
            self.tray.notify(
                "Configuração da OpenAI salva"
                if updated.api_key
                else "Chave da OpenAI não informada — o atalho da API ficará desativado"
            )
        return None

    def open_config(self) -> None:
        """Open .env in the default editor (creates it from the example first)."""
        import os

        env_file = constants.ENV_FILE
        if not env_file.exists() and constants.ENV_EXAMPLE_FILE.exists():
            env_file.write_text(
                constants.ENV_EXAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8"
            )
        if env_file.exists():
            os.startfile(str(Path(env_file)))
        else:  # pragma: no cover - defensive
            logger.warning("No .env file to open")

    def open_logs(self) -> None:
        import os

        constants.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(constants.LOGS_DIR))

    def request_quit(self) -> None:
        """Quit from the tray (stops the Tk loop; main() finalises shutdown)."""
        logger.info("Quit requested from tray")
        if self.overlay is not None:
            self.overlay.stop()
        else:  # pragma: no cover - headless mode
            self.shutdown()

    # ------------------------------------------------------------------ helpers
    def _show_error(self, message: str) -> None:
        if self.overlay is None or not self.settings.overlay.enabled:
            return
        try:
            self.overlay.show_error(message)
        except Exception as exc:  # pragma: no cover - UI must not crash
            logger.debug(f"Overlay error display failed: {exc}")

    def _show_overlay(
        self,
        action: str,
        text: str = "",
        mode: TranscriptionMode = TranscriptionMode.LOCAL,
    ) -> None:
        if self.overlay is None or not self.settings.overlay.enabled:
            return
        try:
            cloud = mode is TranscriptionMode.CLOUD
            if action == "listening":
                self.overlay.show_listening(cloud=cloud)
            elif action == "processing":
                self.overlay.show_processing(cloud=cloud)
            elif action == "success":
                self.overlay.show_success(text)
            else:
                self.overlay.hide()
        except Exception as exc:  # pragma: no cover - UI must not crash
            logger.debug(f"Overlay update failed: {exc}")
