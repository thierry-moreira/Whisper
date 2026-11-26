"""Tests for the text injector (fake clipboard / key sender)."""

from __future__ import annotations

import pytest

from whisper_free.input.injector import (
    InjectorSettings,
    InjectResult,
    TextInjector,
    _SendInputKeySender,
)
from whisper_free.utils.helpers import is_windows


class FakeClipboard:
    def __init__(self):
        self.content = ""
        self.history = []

    def paste(self) -> str:
        return self.content

    def copy(self, text: str) -> None:
        self.history.append(text)
        self.content = text


class FakeKeySender:
    def __init__(self):
        self.sent_ctrl_v = 0
        self.typed: list[str] = []

    def send_ctrl_v(self) -> None:
        self.sent_ctrl_v += 1

    def type_text(self, text: str, interval_s: float) -> None:
        self.typed.append(text)


class TestTextInjectorPaste:
    def test_paste_mode_uses_clipboard_and_ctrl_v(self):
        settings = InjectorSettings(mode="paste", restore_clipboard=True, pre_inject_delay_s=0.0)
        clipboard = FakeClipboard()
        clipboard.content = "original"
        key_sender = FakeKeySender()

        injector = TextInjector(settings, clipboard=clipboard, key_sender=key_sender)
        result = injector.inject("novo texto")

        assert result.success
        assert result.method == "paste"
        assert clipboard.history == ["novo texto", "original"]  # restore happened
        assert key_sender.sent_ctrl_v == 1

    def test_paste_without_restore(self):
        settings = InjectorSettings(mode="paste", restore_clipboard=False, pre_inject_delay_s=0.0)
        clipboard = FakeClipboard()
        key_sender = FakeKeySender()

        injector = TextInjector(settings, clipboard=clipboard, key_sender=key_sender)
        result = injector.inject("texto")

        assert result.success
        assert clipboard.history == ["texto"]

    def test_empty_text_no_op(self):
        settings = InjectorSettings(mode="paste", pre_inject_delay_s=0.0)
        clipboard = FakeClipboard()
        key_sender = FakeKeySender()

        injector = TextInjector(settings, clipboard=clipboard, key_sender=key_sender)
        result = injector.inject("")

        assert result.success
        assert result.method == "none"
        assert clipboard.history == []


class TestTextInjectorType:
    def test_type_mode_sends_unicode(self):
        settings = InjectorSettings(mode="type", char_interval_s=0.0, pre_inject_delay_s=0.0)
        key_sender = FakeKeySender()

        injector = TextInjector(settings, key_sender=key_sender)
        result = injector.inject("Olá 👋")

        assert result.success
        assert result.method == "type"
        assert key_sender.typed == ["Olá 👋"]


class TestInjectResult:
    def test_success_fields(self):
        r = InjectResult(text="x", method="paste", success=True)
        assert r.error is None

    def test_failure_fields(self):
        r = InjectResult(text="x", method="paste", success=False, error="boom")
        assert r.error == "boom"


class ExplodingClipboard(FakeClipboard):
    """Clipboard that refuses writes (locked by another process)."""

    def copy(self, text: str) -> None:
        raise OSError("clipboard is locked")


class TestTextInjectorFallback:
    def test_paste_failure_falls_back_to_type(self):
        settings = InjectorSettings(mode="paste", fallback_to_type=True, pre_inject_delay_s=0.0)
        key_sender = FakeKeySender()
        injector = TextInjector(settings, clipboard=ExplodingClipboard(), key_sender=key_sender)

        result = injector.inject("Olá mundo")

        assert result.success
        assert result.method == "type"
        assert key_sender.typed == ["Olá mundo"]
        assert key_sender.sent_ctrl_v == 0

    def test_fallback_disabled_returns_error(self):
        settings = InjectorSettings(mode="paste", fallback_to_type=False, pre_inject_delay_s=0.0)
        key_sender = FakeKeySender()
        injector = TextInjector(settings, clipboard=ExplodingClipboard(), key_sender=key_sender)

        result = injector.inject("Olá mundo")

        assert not result.success
        assert result.method == "paste"
        assert result.error is not None and "clipboard" in result.error
        assert key_sender.typed == []

    def test_successful_paste_does_not_type(self):
        settings = InjectorSettings(mode="paste", fallback_to_type=True, pre_inject_delay_s=0.0)
        key_sender = FakeKeySender()
        injector = TextInjector(settings, clipboard=FakeClipboard(), key_sender=key_sender)

        result = injector.inject("texto")

        assert result.method == "paste"
        assert key_sender.typed == []


@pytest.mark.skipif(not is_windows(), reason="SendInput only available on Windows")
class TestSendInputEvents:
    """Exercise the SendInput structures without touching the real desktop."""

    def test_ctrl_v_builds_four_events(self):
        sender = _SendInputKeySender()
        sent: list = []
        sender._send = lambda inputs: sent.extend(inputs)  # type: ignore[method-assign]

        sender.send_ctrl_v()

        assert len(sent) == 4

    def test_type_text_encodes_surrogate_pairs(self):
        sender = _SendInputKeySender()
        sent: list = []
        sender._send = lambda inputs: sent.extend(inputs)  # type: ignore[method-assign]

        sender.type_text("a👋", interval_s=0.0)

        # 'a' -> 1 code unit, '👋' -> 2 surrogate units, 2 events per unit.
        assert len(sent) == 6
