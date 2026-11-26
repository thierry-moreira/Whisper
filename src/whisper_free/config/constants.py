"""Application-wide constants.

Central place for names, version, paths and default values that do not
belong in user-configurable settings.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
APP_NAME = "Whisper Free"
APP_SLUG = "whisper_free"
APP_VERSION = "0.1.0"
APP_MUTEX_NAME = "Global\\WhisperFree_SingleInstance_Mutex"

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------
# Paths must work in three layouts: source checkout, editable install and
# regular wheel install.  ``parents[3]`` is only correct for a source checkout;
# in site-packages it points at ``Lib`` (or the venv root), which is not a
# writable application directory.
_THIS_FILE = Path(__file__).resolve()
PACKAGE_DIR = _THIS_FILE.parents[1]  # .../whisper_free
SRC_DIR = _THIS_FILE.parents[2]  # .../src (checkout) or site-packages


def _resolve_project_root() -> Path:
    override = os.environ.get("WHISPER_FREE_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):  # PyInstaller/Nuitka bundle
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / APP_NAME
    source_root = SRC_DIR.parent
    if (source_root / "pyproject.toml").is_file():
        return source_root
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / APP_NAME


PROJECT_ROOT = _resolve_project_root()

# ---------------------------------------------------------------------------
# Default directories (relative to project root, portable-first approach)
# ---------------------------------------------------------------------------
MODELS_DIR = PROJECT_ROOT / "models"
LOGS_DIR = PROJECT_ROOT / "logs"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
JRE_DIR = RUNTIME_DIR / "jre"
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
TARGET_SAMPLE_RATE = 16_000  # whisper expects 16 kHz mono
AUDIO_CHANNELS = 1
AUDIO_DTYPE = "int16"
AUDIO_BLOCKSIZE = 1024  # ~64ms @ 16kHz
MIN_RECORDING_SECONDS = 0.3  # ignore ultra-short accidental presses

# ---------------------------------------------------------------------------
# Whisper
# ---------------------------------------------------------------------------
WHISPER_MODEL_SIZES = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
    "large-v3-turbo",
    "distil-large-v3",
)
DEFAULT_WHISPER_MODEL = "large-v3-turbo"
DEFAULT_COMPUTE_TYPE = "int8_float16"
DEFAULT_IDLE_UNLOAD_SECONDS = 60  # used only when unload_after_use is false
DEFAULT_UNLOAD_AFTER_USE = True  # free the GPU as soon as a dictation ends

# ---------------------------------------------------------------------------
# Grammar (LanguageTool)
# ---------------------------------------------------------------------------
DEFAULT_GRAMMAR_LANGUAGE = "pt-BR"
# LanguageTool 6.x requires Java 17+; the java_runtime manager always
# enforces that minimum.
# Eclipse Temurin JRE 17 (Adoptium) - using Adoptium API mirror (always latest stable)
JRE_DOWNLOAD_URL = (
    "https://github.com/adoptium/temurin17-binaries/releases/download/"
    "jdk-17.0.20.1%2B1/OpenJDK17U-jre_x64_windows_hotspot_17.0.20.1_1.zip"
)
JAVA_MIN_MAJOR = 17

# ---------------------------------------------------------------------------
# Hotkeys
# ---------------------------------------------------------------------------
DEFAULT_HOTKEY_TRIGGER = "ctrl+shift+space"
DEFAULT_HOTKEY_CLOUD_TRIGGER = "ctrl+alt+space"
DEFAULT_HOTKEY_TOGGLE_ENABLED = "ctrl+shift+f12"

# ---------------------------------------------------------------------------
# OpenAI cloud transcription
# ---------------------------------------------------------------------------
DEFAULT_OPENAI_MODEL = "gpt-4o-transcribe"
OPENAI_MODELS = ("gpt-4o-transcribe", "gpt-4o-mini-transcribe", "whisper-1")
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 60.0
OPENAI_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # official limit for /audio/transcriptions

# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------
OVERLAY_WIDTH = 216
OVERLAY_HEIGHT = 44
OVERLAY_MARGIN = 56  # px from screen edge (top-center / bottom-center)
OVERLAY_FPS_MS = 33  # ~30 fps redraw interval for animations

# ---------------------------------------------------------------------------
# Limits / timeouts
# ---------------------------------------------------------------------------
MAX_RECORDING_SECONDS = 120  # hard cap — auto-stop after 2 minutes
HOTKEY_PRESS_DEBOUNCE_S = 0.15  # ignore duplicate key events within this window
