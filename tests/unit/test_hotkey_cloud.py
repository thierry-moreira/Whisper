"""Tests for the cloud (OpenAI) hotkey binding."""

from __future__ import annotations

from whisper_free.config.settings import HotkeySettings
from whisper_free.input.hotkey import HotkeyCallbacks, HotkeyManager


def make_manager(cloud: bool, mode: str = "hold"):
    calls = []

    def press():
        calls.append("local-press")

    def release():
        calls.append("local-release")

    def toggle():
        calls.append("toggle-enabled")

    def cloud_press():
        calls.append("cloud-press")

    def cloud_release():
        calls.append("cloud-release")

    manager = HotkeyManager(
        settings=HotkeySettings(
            mode=mode, trigger="ctrl+shift+space", cloud_trigger="ctrl+alt+space"
        ),
        callbacks=HotkeyCallbacks(
            press,
            release,
            toggle,
            on_cloud_press=cloud_press if cloud else None,
            on_cloud_release=cloud_release if cloud else None,
        ),
    )
    return manager, calls


class TestCloudHotkeyRegistration:
    def test_hold_mode_registers_five(self, fake_hotkey_backend):
        manager, _ = make_manager(cloud=True)
        manager._backend = fake_hotkey_backend
        manager.register()

        assert len(fake_hotkey_backend.registered) == 5
        # order: local press, local release, cloud press, cloud release, toggle-enabled
        hotkeys = [entry[0] for entry in fake_hotkey_backend.registered]
        assert hotkeys == [
            "ctrl+shift+space",
            "ctrl+shift+space",
            "ctrl+alt+space",
            "ctrl+alt+space",
            "ctrl+shift+f12",
        ]

    def test_toggle_mode_registers_three(self, fake_hotkey_backend):
        manager, _ = make_manager(cloud=True, mode="toggle")
        manager._backend = fake_hotkey_backend
        manager.register()

        assert len(fake_hotkey_backend.registered) == 3

    def test_without_cloud_callbacks_registers_three(self, fake_hotkey_backend):
        manager, _ = make_manager(cloud=False)
        manager._backend = fake_hotkey_backend
        manager.register()

        assert len(fake_hotkey_backend.registered) == 3


class TestCloudHotkeyCallbacks:
    def test_cloud_press_release_triggered(self, fake_hotkey_backend):
        manager, calls = make_manager(cloud=True)
        manager._backend = fake_hotkey_backend
        manager.register()

        fake_hotkey_backend.get_callback(2)()  # cloud press
        fake_hotkey_backend.get_callback(3)()  # cloud release

        assert calls == ["cloud-press", "cloud-release"]

    def test_local_release_does_not_trigger_cloud_release(self, fake_hotkey_backend):
        manager, calls = make_manager(cloud=True)
        manager._backend = fake_hotkey_backend
        manager.register()

        fake_hotkey_backend.get_callback(0)()  # local press
        fake_hotkey_backend.get_callback(3)()  # cloud release (must be ignored)

        assert calls == ["local-press"]

    def test_cloud_press_does_not_trigger_local_press(self, fake_hotkey_backend):
        manager, calls = make_manager(cloud=True)
        manager._backend = fake_hotkey_backend
        manager.register()

        fake_hotkey_backend.get_callback(2)()  # cloud press
        fake_hotkey_backend.get_callback(1)()  # local release (must be ignored)

        assert calls == ["cloud-press"]
