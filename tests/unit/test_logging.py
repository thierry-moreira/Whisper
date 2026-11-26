"""Tests for logging setup: pythonw (no stderr) and --silent."""

from __future__ import annotations

import pytest
from loguru import logger

from whisper_free.utils import logging as logging_module


@pytest.fixture(autouse=True)
def _reset_logging():
    yield
    logger.complete()
    logger.remove()
    logging_module._configured = False


class TestSetupLogging:
    def test_returns_log_path(self, tmp_path):
        log_file = logging_module.setup_logging("DEBUG", log_dir=tmp_path)

        assert log_file == tmp_path / "whisper_free.log"
        assert log_file.exists()

    def test_silent_mode_writes_only_to_file(self, tmp_path):
        log_file = logging_module.setup_logging("INFO", log_dir=tmp_path, console=False)

        logger.bind(name="test").info("silent message")
        logger.complete()

        assert "silent message" in log_file.read_text(encoding="utf-8")

    def test_missing_stderr_does_not_crash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(logging_module.sys, "stderr", None)

        log_file = logging_module.setup_logging("INFO", log_dir=tmp_path, console=True)
        logger.bind(name="test").info("pythonw message")
        logger.complete()

        assert "pythonw message" in log_file.read_text(encoding="utf-8")
