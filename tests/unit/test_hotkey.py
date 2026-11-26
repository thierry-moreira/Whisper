"""Tests for the hotkey manager and debouncing."""

from __future__ import annotations

import pytest

from whisper_free.input.hotkey import HotkeyCallbacks, HotkeyManager, parse_hotkey


class TestParseHotkey:
    def test_simple(self):
        assert parse_hotkey("ctrl+shift+space") == ["ctrl", "shift", "space"]

    def test_spaces_and_case(self):
        assert parse_hotkey("CTRL + SHIFT + SPACE") == ["ctrl", "shift", "space"]

    def test_empty_parts_ignored(self):
        assert parse_hotkey("ctrl++space") == ["ctrl", "space"]


class TestHotkeyManager:
    def test_register_and_unregister(self, fake_hotkey_backend):
        calls = []

        def press():
            calls.append("press")

        def release():
            calls.append("release")

        def toggle():
            calls.append("toggle")

        manager = HotkeyManager(
            settings=None,
            callbacks=HotkeyCallbacks(press, release, toggle),
            backend=fake_hotkey_backend,
        )
        # monkey-patch settings
        from whisper_free.config.settings import HotkeySettings

        manager._settings = HotkeySettings(
            mode="hold", trigger="ctrl+shift+space", toggle_enabled="ctrl+shift+f12"
        )
        manager.register()
        assert len(fake_hotkey_backend.registered) == 3
        handles = list(manager._handles)
        manager.unregister()
        assert fake_hotkey_backend.removed == handles
        assert manager._handles == []

    def test_partial_registration_failure_cleans_up(self):
        class ExplodingBackend:
            def __init__(self):
                self.added = 0
                self.removed = []

            def add_hotkey(self, hotkey, callback, **kwargs):
                self.added += 1
                if self.added == 3:
                    raise RuntimeError("hook limit reached")

                def remove():
                    self.removed.append(remove)

                return remove

            def remove_hotkey(self, handle):
                self.removed.append(handle)

        from whisper_free.config.settings import HotkeySettings

        backend = ExplodingBackend()
        manager = HotkeyManager(
            HotkeySettings(mode="hold", trigger="ctrl+shift+space"),
            HotkeyCallbacks(lambda: None, lambda: None, lambda: None),
            backend=backend,
        )
        with pytest.raises(RuntimeError):
            manager.register()
        assert not manager.is_registered
        assert manager._handles == []
        assert len(backend.removed) == 2

    def test_hold_mode_press_release(self, fake_hotkey_backend):
        calls = []

        def press():
            calls.append("press")

        def release():
            calls.append("release")

        manager = HotkeyManager(
            settings=None,
            callbacks=HotkeyCallbacks(press, release, lambda: None),
            backend=fake_hotkey_backend,
        )
        from whisper_free.config.settings import HotkeySettings

        manager._settings = HotkeySettings(mode="hold", trigger="ctrl+shift+space")
        manager.register()

        # fire the press callback (index 0)
        cb = fake_hotkey_backend.get_callback(0)
        cb()
        assert calls == ["press"]

        # fire the release callback (index 1, trigger_on_release)
        cb = fake_hotkey_backend.get_callback(1)
        cb()
        assert calls == ["press", "release"]

    def test_debounce_ignores_rapid_duplicate(self, fake_hotkey_backend):
        calls = []

        def press():
            calls.append("press")

        manager = HotkeyManager(
            settings=None,
            callbacks=HotkeyCallbacks(press, lambda: None, lambda: None),
            backend=fake_hotkey_backend,
        )
        from whisper_free.config.settings import HotkeySettings

        manager._settings = HotkeySettings(mode="hold", trigger="ctrl+shift+space")
        manager.register()

        cb = fake_hotkey_backend.get_callback(0)
        cb()  # first press
        cb()  # immediate duplicate
        assert calls == ["press"]
