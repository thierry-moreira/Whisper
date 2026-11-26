"""Tests for the Windows startup registry integration."""

from __future__ import annotations

from whisper_free.startup.windows import WindowsStartup


class TestWindowsStartup:
    def test_build_command_dev_mode(self):
        startup = WindowsStartup()
        cmd = startup.build_command()
        assert "pythonw.exe" in cmd or "pythonw" in cmd

    def test_build_command_frozen_mode(self, monkeypatch):
        import whisper_free.startup.windows as w

        monkeypatch.setattr(w, "is_frozen", lambda: True)
        monkeypatch.setattr(w, "pythonw_executable", lambda: "pythonw.exe")
        startup = WindowsStartup()
        cmd = startup.build_command()
        assert cmd == '"pythonw.exe" --silent'

    def test_disable_idempotent(self, monkeypatch):
        startup = WindowsStartup()
        # Just verify the method doesn't raise when the key doesn't exist
        startup.disable()
