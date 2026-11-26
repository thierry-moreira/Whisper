"""Tests for the .env updater utility."""

from __future__ import annotations

from whisper_free.config.env_store import update_env_file


class TestUpdateEnvFile:
    def test_creates_file_when_missing(self, tmp_path):
        path = tmp_path / ".env"
        update_env_file(path, {"WHISPER_FREE_OPENAI__API_KEY": "sk-x"})
        content = path.read_text(encoding="utf-8")
        assert "WHISPER_FREE_OPENAI__API_KEY=sk-x" in content

    def test_updates_existing_key_preserving_comments(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("# comment\nWHISPER_FREE_LOG_LEVEL=INFO\n", encoding="utf-8")

        update_env_file(path, {"WHISPER_FREE_LOG_LEVEL": "DEBUG"})

        content = path.read_text(encoding="utf-8")
        assert "# comment" in content
        assert "WHISPER_FREE_LOG_LEVEL=DEBUG" in content
        assert "WHISPER_FREE_LOG_LEVEL=INFO" not in content

    def test_appends_missing_key(self, tmp_path):
        path = tmp_path / ".env"
        path.write_text("A=1\n", encoding="utf-8")

        update_env_file(path, {"B": "2"})

        content = path.read_text(encoding="utf-8")
        assert "A=1" in content
        assert "B=2" in content

    def test_strips_newlines_in_value(self, tmp_path):
        path = tmp_path / ".env"
        update_env_file(path, {"KEY": "line1\nline2"})
        assert "KEY=line1 line2" in path.read_text(encoding="utf-8")
