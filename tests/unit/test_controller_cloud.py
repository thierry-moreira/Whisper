"""Tests for the controller's cloud dictation flow and OpenAI config."""

from __future__ import annotations

import numpy as np

from whisper_free.core.states import AppState


class TestCloudHotkeyFlow:
    def test_cloud_press_without_key_shows_error(self, controller, fake_overlay, fake_tray):
        controller.start()
        controller.settings.openai.api_key = ""

        controller.on_cloud_hotkey_press()

        assert controller.state == AppState.IDLE
        assert "error" in fake_overlay.states()
        assert fake_tray.notifications  # warned the user

    def test_cloud_press_with_key_starts_listening(self, controller, fake_capture):
        controller.start()
        controller.settings.openai.api_key = "sk-test"

        controller.on_cloud_hotkey_press()

        assert controller.state == AppState.LISTENING
        assert fake_capture.is_running

    def test_cloud_release_processes_with_cloud_mode(
        self, controller, fake_capture, inline_executor, fake_pipeline
    ):
        controller.start()
        controller.settings.openai.api_key = "sk-test"

        controller.on_cloud_hotkey_press()
        fake_capture.push(np.zeros((8000, 1), dtype="int16"))
        controller.on_cloud_hotkey_release()
        inline_executor.run_pending()

        from whisper_free.transcription.pipeline import TranscriptionMode

        assert fake_pipeline.modes == [TranscriptionMode.CLOUD]
        assert controller.state == AppState.IDLE

    def test_local_release_ignored_while_cloud_listening(self, controller, fake_capture):
        controller.start()
        controller.settings.openai.api_key = "sk-test"

        controller.on_cloud_hotkey_press()
        controller.on_hotkey_release()  # local release must be ignored

        assert controller.state == AppState.LISTENING
        assert fake_capture.is_running


class TestOpenAIConfig:
    def test_save_updates_settings_and_env(self, controller, tmp_path):
        env_path = tmp_path / ".env"

        error = controller._save_openai_settings(
            "sk-new-key",
            "gpt-4o-mini-transcribe",
            "https://api.example.com/v1",
            env_path=env_path,
        )

        assert error is None
        assert controller.settings.openai.api_key == "sk-new-key"
        assert controller.settings.openai.model == "gpt-4o-mini-transcribe"
        content = env_path.read_text(encoding="utf-8")
        assert "WHISPER_FREE_OPENAI__API_KEY=sk-new-key" in content
        assert "WHISPER_FREE_OPENAI__MODEL=gpt-4o-mini-transcribe" in content

    def test_save_rejects_invalid_base_url(self, controller, tmp_path):
        env_path = tmp_path / ".env"

        error = controller._save_openai_settings(
            "sk-new-key", "gpt-4o-transcribe", "ftp://bad", env_path=env_path
        )

        assert error is not None
        assert "base_url" in error

    def test_is_openai_configured(self, controller):
        controller.settings.openai.api_key = "sk-test"
        assert controller.is_openai_configured() is True
        controller.settings.openai.api_key = ""
        assert controller.is_openai_configured() is False

    def test_open_settings_uses_overlay_dialog(self, controller, fake_overlay):
        controller.overlay = fake_overlay
        controller.open_openai_settings()
        assert fake_overlay.openai_dialog is not None
        assert fake_overlay.openai_dialog["model"] == controller.settings.openai.model
