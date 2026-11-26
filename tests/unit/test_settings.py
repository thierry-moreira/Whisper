"""Tests for settings validation and defaults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from whisper_free.config.constants import DEFAULT_COMPUTE_TYPE, DEFAULT_WHISPER_MODEL
from whisper_free.config.settings import (
    AudioSettings,
    GrammarSettings,
    HotkeySettings,
    InjectorSettings,
    Settings,
    WhisperSettings,
    load_settings,
)


class TestDefaults:
    def test_default_model_and_compute(self):
        s = Settings()
        assert s.whisper.model_size == DEFAULT_WHISPER_MODEL
        assert s.whisper.compute_type == DEFAULT_COMPUTE_TYPE

    def test_default_hotkey(self):
        s = Settings()
        assert s.hotkey.trigger == "ctrl+shift+space"
        assert s.hotkey.mode == "hold"

    def test_nested_defaults_are_independent(self):
        a, b = Settings(), Settings()
        a.whisper.beam_size = 9
        assert b.whisper.beam_size == 5  # no shared mutable state

    def test_fallback_and_idle_defaults(self):
        s = Settings()
        assert s.whisper.fallback_to_cpu is True
        assert s.whisper.idle_unload_seconds == 60
        assert s.whisper.unload_after_use is True
        assert s.injector.fallback_to_type is True

    def test_audio_defaults_come_from_constants(self):
        from whisper_free.config import constants

        s = Settings()
        assert s.audio.sample_rate == constants.TARGET_SAMPLE_RATE
        assert s.audio.channels == constants.AUDIO_CHANNELS
        assert s.audio.blocksize == constants.AUDIO_BLOCKSIZE


class TestWhisperSettings:
    def test_rejects_unknown_model(self):
        with pytest.raises(ValidationError):
            WhisperSettings(model_size="not-a-model")

    def test_accepts_known_model(self):
        assert WhisperSettings(model_size="large-v3-turbo").model_size == "large-v3-turbo"

    def test_accepts_local_path(self):
        ws = WhisperSettings(model_size="C:/models/my-whisper")
        assert ws.model_size == "C:/models/my-whisper"

    def test_beam_size_bounds(self):
        with pytest.raises(ValidationError):
            WhisperSettings(beam_size=0)
        with pytest.raises(ValidationError):
            WhisperSettings(beam_size=99)

    def test_language_is_normalised(self):
        assert WhisperSettings(language="  PT  ").language == "pt"

    def test_invalid_device_rejected(self):
        with pytest.raises(ValidationError):
            WhisperSettings(device="tpu")


class TestHotkeySettings:
    def test_hotkey_normalised(self):
        hk = HotkeySettings(trigger="CTRL + SHIFT + SPACE")
        assert hk.trigger == "ctrl+shift+space"

    def test_empty_hotkey_rejected(self):
        with pytest.raises(ValidationError):
            HotkeySettings(trigger="   ")

    def test_too_many_keys_rejected(self):
        with pytest.raises(ValidationError):
            HotkeySettings(trigger="ctrl+alt+shift+win+space")

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            HotkeySettings(mode="press")


class TestOtherGroups:
    def test_audio_sample_rate_bounds(self):
        with pytest.raises(ValidationError):
            AudioSettings(sample_rate=100)

    def test_grammar_timeout_positive(self):
        with pytest.raises(ValidationError):
            GrammarSettings(timeout_seconds=0)

    def test_injector_mode_validated(self):
        with pytest.raises(ValidationError):
            InjectorSettings(mode="clipboard")

    def test_injector_delay_bounds(self):
        with pytest.raises(ValidationError):
            InjectorSettings(pre_inject_delay_s=5)


class TestLoadSettings:
    def test_load_returns_settings(self):
        assert isinstance(load_settings(), Settings)

    def test_overrides_applied(self):
        s = load_settings(log_level="DEBUG")
        assert s.log_level == "DEBUG"
