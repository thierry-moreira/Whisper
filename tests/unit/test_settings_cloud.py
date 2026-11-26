"""Tests for OpenAI settings and cloud hotkey validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from whisper_free.config.settings import HotkeySettings, OpenAISettings


class TestOpenAISettings:
    def test_defaults(self):
        s = OpenAISettings()
        assert s.model == "gpt-4o-transcribe"
        assert s.base_url == "https://api.openai.com/v1"
        assert s.api_key == ""
        assert s.enabled is True

    def test_strips_api_key_and_model(self):
        s = OpenAISettings(api_key="  sk-abc  ", model="  gpt-4o-mini-transcribe  ")
        assert s.api_key == "sk-abc"
        assert s.model == "gpt-4o-mini-transcribe"

    def test_empty_model_rejected(self):
        with pytest.raises(ValidationError):
            OpenAISettings(model="   ")

    def test_invalid_base_url_rejected(self):
        with pytest.raises(ValidationError):
            OpenAISettings(base_url="ftp://bad")

    def test_base_url_defaults_when_empty(self):
        s = OpenAISettings(base_url="")
        assert s.base_url == "https://api.openai.com/v1"

    def test_language_normalised(self):
        assert OpenAISettings(language="  PT  ").language == "pt"

    def test_timeout_bounds(self):
        with pytest.raises(ValidationError):
            OpenAISettings(timeout_seconds=0)
        with pytest.raises(ValidationError):
            OpenAISettings(timeout_seconds=400)


class TestHotkeyValidation:
    def test_cloud_trigger_default(self):
        s = HotkeySettings()
        assert s.cloud_trigger == "ctrl+alt+space"

    def test_duplicate_hotkeys_rejected(self):
        with pytest.raises(ValidationError):
            HotkeySettings(trigger="ctrl+shift+space", cloud_trigger="ctrl+shift+space")

    def test_duplicate_with_toggle_rejected(self):
        with pytest.raises(ValidationError):
            HotkeySettings(toggle_enabled="ctrl+shift+space")

    def test_all_distinct_accepted(self):
        s = HotkeySettings(
            trigger="ctrl+shift+space",
            cloud_trigger="ctrl+alt+space",
            toggle_enabled="ctrl+shift+f12",
        )
        assert s.cloud_trigger == "ctrl+alt+space"
