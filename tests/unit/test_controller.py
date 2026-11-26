"""Tests for the controller state machine and orchestration."""

from __future__ import annotations

import numpy as np

from whisper_free.core.states import AppState


class TestControllerLifecycle:
    def test_start_registers_hotkey(self, controller):
        controller.start()
        assert controller.hotkey.is_registered

    def test_shutdown_unregisters_hotkey(self, controller):
        controller.start()
        controller.shutdown()
        assert not controller.hotkey.is_registered

    def test_shutdown_idempotent(self, controller):
        controller.shutdown()
        controller.shutdown()  # second call must not crash

    def test_prepare_async_called(self, controller, fake_pipeline):
        controller.start()
        assert fake_pipeline.prepare_calls == 1


class TestHotkeyPressRelease:
    def test_press_when_idle_starts_listening(self, controller, fake_capture):
        controller.start()
        controller.on_hotkey_press()

        assert controller.state == AppState.LISTENING
        assert fake_capture.start_calls == 1
        assert fake_capture.is_running

    def test_press_when_not_idle_ignored(self, controller):
        controller.start()
        controller.on_hotkey_press()  # -> LISTENING
        controller.on_hotkey_press()  # duplicate while listening
        assert controller.state == AppState.LISTENING

    def test_release_when_listening_triggers_processing(
        self, controller, fake_capture, inline_executor
    ):
        controller.start()
        controller.on_hotkey_press()  # LISTENING
        fake_capture.push(np.zeros((8000, 1), dtype="int16"))  # 0.5s > MIN_RECORDING_SECONDS (0.3s)
        controller.on_hotkey_release()

        assert controller.state == AppState.PROCESSING
        assert inline_executor.jobs  # pipeline job submitted
        inline_executor.run_pending()  # execute synchronously
        assert controller.state == AppState.IDLE

    def test_release_transitions_listening_processing_injecting_idle(
        self, controller, fake_capture, inline_executor, fake_overlay
    ):
        """Verify the full state sequence by capturing intermediate states."""
        controller.start()
        observed: list[AppState] = []
        controller._on_state_change = lambda s: observed.append(s)

        controller.on_hotkey_press()
        fake_capture.push(np.zeros((8000, 1), dtype="int16"))
        controller.on_hotkey_release()
        inline_executor.run_pending()

        assert observed == [
            AppState.LISTENING,
            AppState.PROCESSING,
            AppState.INJECTING,
            AppState.IDLE,
        ]

    def test_release_below_min_duration_aborts(self, controller, fake_capture):
        controller.start()
        controller.on_hotkey_press()  # LISTENING
        fake_capture.push(np.zeros((100, 1), dtype="int16"))  # too short
        controller.on_hotkey_release()

        assert controller.state == AppState.IDLE
        assert fake_capture.stop_calls == 1

    def test_disabled_ignores_hotkey(self, controller):
        controller.start()
        controller.toggle_enabled()  # DISABLED
        controller.on_hotkey_press()
        assert controller.state == AppState.DISABLED

    def test_toggle_while_listening_stops_capture(self, controller, fake_capture):
        controller.start()
        controller.on_hotkey_press()  # LISTENING
        controller.toggle_enabled()  # DISABLED
        assert controller.state == AppState.DISABLED
        assert fake_capture.stop_calls == 1


class TestOverlaySignals:
    def test_overlay_shows_listening(self, controller, fake_overlay):
        controller.start()
        controller.on_hotkey_press()
        assert "listening" in fake_overlay.states()

    def test_overlay_shows_processing(
        self, controller, fake_overlay, fake_capture, inline_executor
    ):
        controller.start()
        controller.on_hotkey_press()
        fake_capture.push(np.zeros((8000, 1), dtype="int16"))
        controller.on_hotkey_release()
        inline_executor.run_pending()
        assert "processing" in fake_overlay.states()

    def test_overlay_shows_success(
        self, controller, fake_overlay, fake_capture, inline_executor, fake_pipeline
    ):
        controller.start()
        controller.on_hotkey_press()
        fake_capture.push(np.zeros((8000, 1), dtype="int16"))
        controller.on_hotkey_release()
        inline_executor.run_pending()
        assert "success" in fake_overlay.states()

    def test_overlay_shows_error_on_failure(
        self, controller, fake_overlay, fake_capture, inline_executor, fake_pipeline
    ):
        fake_pipeline.error = "falha simulada"
        controller.start()
        controller.on_hotkey_press()
        fake_capture.push(np.zeros((8000, 1), dtype="int16"))
        controller.on_hotkey_release()
        inline_executor.run_pending()
        assert "error" in fake_overlay.states()


class TestAutostartSync:
    def test_enable_when_desired(self, controller, fake_startup):
        controller.settings.startup.auto_start = True
        fake_startup._enabled = False
        controller._sync_autostart()
        assert fake_startup._enabled is True
        assert True in fake_startup.set_calls

    def test_disable_when_not_desired(self, controller, fake_startup):
        controller.settings.startup.auto_start = False
        fake_startup._enabled = True
        controller._sync_autostart()
        assert fake_startup._enabled is False
        assert False in fake_startup.set_calls

    def test_no_change_when_already_correct(self, controller, fake_startup):
        controller.settings.startup.auto_start = True
        fake_startup._enabled = True
        fake_startup.set_calls.clear()
        controller._sync_autostart()
        assert fake_startup.set_calls == []


class TestTrayActions:
    def test_toggle_enabled_refreshes_tray(self, controller, fake_tray):
        controller.start()
        controller.toggle_enabled()  # -> DISABLED
        assert fake_tray.refreshes == 1
        assert "Assistente desativado" in fake_tray.notifications

        controller.toggle_enabled()  # -> IDLE
        assert fake_tray.refreshes == 2
        assert "Assistente ativado" in fake_tray.notifications

    def test_toggle_overlay(self, controller, fake_tray):
        controller.start()
        controller.toggle_overlay()
        assert controller.settings.overlay.enabled is False
        assert fake_tray.refreshes == 1

    def test_warmup_called(self, controller, fake_pipeline):
        controller.start()
        controller.warmup()
        assert fake_pipeline.warmup_calls == 1

    def test_autostart_toggle(self, controller, fake_startup, fake_tray):
        controller.start()
        controller.toggle_autostart()
        assert fake_startup.set_calls[-1] is not None
        assert fake_tray.refreshes == 1

    def test_request_quit_stops_overlay(self, controller, fake_overlay):
        controller.start()
        controller.request_quit()
        assert fake_overlay.stopped


class TestDisableDuringProcessing:
    """A disable that lands mid-transcription must never inject or raise."""

    @staticmethod
    def _start_processing(controller, fake_capture):
        controller.start()
        controller.on_hotkey_press()
        fake_capture.push(np.zeros((8000, 1), dtype="int16"))
        controller.on_hotkey_release()
        assert controller.state == AppState.PROCESSING

    def test_disable_discards_pending_result(
        self, controller, fake_capture, fake_injector, fake_pipeline, inline_executor
    ):
        self._start_processing(controller, fake_capture)

        controller.toggle_enabled()
        assert controller.state == AppState.DISABLED
        assert fake_pipeline.release_calls == 1  # GPU released on disable

        inline_executor.run_pending()  # must not raise StateTransitionError
        assert controller.state == AppState.DISABLED
        assert fake_injector.injected == []

    def test_disable_then_enable_still_discards_result(
        self, controller, fake_capture, fake_injector, inline_executor
    ):
        self._start_processing(controller, fake_capture)

        controller.toggle_enabled()  # DISABLED
        controller.toggle_enabled()  # IDLE again
        assert controller.state == AppState.IDLE

        inline_executor.run_pending()
        assert controller.state == AppState.IDLE
        assert fake_injector.injected == []

    def test_successful_dictation_keeps_model_warm(
        self, controller, fake_capture, fake_injector, fake_pipeline, inline_executor
    ):
        self._start_processing(controller, fake_capture)

        inline_executor.run_pending()

        assert controller.state == AppState.IDLE
        assert fake_injector.injected == ["Olá mundo."]
        assert fake_pipeline.release_calls == 0

    def test_release_after_disable_is_safe(self, controller, fake_capture):
        controller.start()
        controller.on_hotkey_press()
        controller.toggle_enabled()  # DISABLED while the key is held

        controller.on_hotkey_release()  # must be a no-op, not a transition error
        assert controller.state == AppState.DISABLED
        assert fake_capture.stop_calls == 1


class TestAutoStopTimer:
    def test_timer_fires_after_max_seconds(self, controller, fake_capture, inline_executor):
        controller.start()
        controller.on_hotkey_press()
        controller._auto_stop()
        inline_executor.run_pending()
        assert controller.state == AppState.IDLE
        assert fake_capture.stop_calls == 1

    def test_timer_cancelled_on_manual_stop(self, controller):
        controller.start()
        controller.on_hotkey_press()
        controller._stop_listening()  # should cancel timer
        controller._auto_stop()  # callback fires
        assert controller.state == AppState.IDLE  # no double-stop crash
