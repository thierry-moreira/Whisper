"""Logging configuration built on loguru.

Provides a single :func:`setup_logging` entry point that installs a colourised
console sink (stderr) and a rotating file sink under ``logs/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from whisper_free.config.constants import LOGS_DIR

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
)
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"

_configured = False


def setup_logging(
    level: str = "INFO", log_dir: Path | None = None, *, console: bool = True
) -> Path:
    """Configure loguru sinks. Safe to call multiple times.

    ``console=False`` (``--silent``) keeps only the rotating file sink.
    Under ``pythonw.exe`` ``sys.stderr`` is ``None``; the console sink is
    skipped automatically instead of raising ``TypeError`` at startup.

    Returns the log file path in use.
    """
    global _configured

    directory = log_dir or LOGS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / "whisper_free.log"

    logger.remove()

    # pythonw.exe provides no stderr. A console sink would raise TypeError and
    # prevent the file sink from being installed, so skip it in that case.
    if console and sys.stderr is not None:
        logger.add(
            sys.stderr,
            level=level.upper(),
            format=_CONSOLE_FORMAT,
            colorize=True,
            backtrace=False,
            diagnose=False,
        )
    logger.add(
        log_file,
        level="DEBUG",
        format=_FILE_FORMAT,
        rotation="5 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,  # thread & process safe
        backtrace=True,
        diagnose=False,
    )

    _configured = True
    logger.debug(f"Logging configured (level={level}, file={log_file})")
    return log_file


def get_logger(name: str = "whisper_free"):
    """Return a loguru logger bound to ``name`` (a drop-in logger)."""
    if not _configured:
        setup_logging()
    return logger.bind(name=name)
