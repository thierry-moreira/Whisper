"""Typed, validated application settings.

Reads defaults from :mod:`whisper_free.config.constants` and allows overriding
via a ``.env`` file (and/or real environment variables) using the
``WHISPER_FREE_`` prefix with ``__`` as nested delimiter, e.g.::

    WHISPER_FREE_WHISPER__MODEL_SIZE=large-v3
    WHISPER_FREE_HOTKEY__TRIGGER=ctrl+alt+space
    WHISPER_FREE_OPENAI__API_KEY=sk-...
"""

from __future__ import annotations

from typing import Literal, Self, cast

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from whisper_free.config.constants import (
    APP_VERSION,
    AUDIO_BLOCKSIZE,
    AUDIO_CHANNELS,
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_GRAMMAR_LANGUAGE,
    DEFAULT_HOTKEY_CLOUD_TRIGGER,
    DEFAULT_HOTKEY_TOGGLE_ENABLED,
    DEFAULT_HOTKEY_TRIGGER,
    DEFAULT_IDLE_UNLOAD_SECONDS,
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENAI_TIMEOUT_SECONDS,
    DEFAULT_UNLOAD_AFTER_USE,
    DEFAULT_WHISPER_MODEL,
    ENV_FILE,
    MODELS_DIR,
    TARGET_SAMPLE_RATE,
    WHISPER_MODEL_SIZES,
)

ComputeType = Literal["int8_float16", "float16", "int8", "float32", "auto"]

# ---------------------------------------------------------------------------
# Nested setting groups
# ---------------------------------------------------------------------------


class WhisperSettings(BaseModel):
    """Speech-to-text engine options."""

    model_size: str = Field(
        default=DEFAULT_WHISPER_MODEL,
        description="Whisper model name (e.g. large-v3-turbo) or local path.",
    )
    device: Literal["cuda", "cpu", "auto"] = "cuda"
    compute_type: ComputeType = cast(ComputeType, DEFAULT_COMPUTE_TYPE)
    language: str = Field(default="pt", description="Spoken language code; empty = auto.")
    beam_size: int = Field(default=5, ge=1, le=10)
    vad_filter: bool = True
    condition_on_previous_text: bool = False
    model_dir: str = Field(default_factory=lambda: str(MODELS_DIR))
    cpu_threads: int = Field(default=0, ge=0, description="0 = auto.")
    fallback_to_cpu: bool = Field(
        default=True,
        description="Retry on CPU (int8) when CUDA cannot be initialised.",
    )
    idle_unload_seconds: int = Field(
        default=DEFAULT_IDLE_UNLOAD_SECONDS,
        ge=0,
        le=3600,
        description="Unload the model after this many idle seconds (0 = never).",
    )
    unload_after_use: bool = Field(
        default=DEFAULT_UNLOAD_AFTER_USE,
        description="Unload the model immediately after each dictation.",
    )

    @field_validator("model_size")
    @classmethod
    def _validate_model_size(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model_size cannot be empty")
        if ("/" in cleaned or "\\" in cleaned) and len(cleaned) > 2:
            return cleaned  # allow local model directories
        if cleaned not in WHISPER_MODEL_SIZES:
            raise ValueError(
                f"Unknown model '{cleaned}'. Valid sizes: {', '.join(WHISPER_MODEL_SIZES)}"
            )
        return cleaned

    @field_validator("language")
    @classmethod
    def _normalize_language(cls, value: str) -> str:
        return value.strip().lower()


class OpenAISettings(BaseModel):
    """Cloud transcription through the OpenAI ``/audio/transcriptions`` API."""

    enabled: bool = True
    api_key: str = Field(
        default="",
        repr=False,
        description="OpenAI API key (sk-...). Kept in the local .env file.",
    )
    model: str = Field(
        default=DEFAULT_OPENAI_MODEL,
        description="Model used by the cloud hotkey (gpt-4o-transcribe, ...).",
    )
    base_url: str = Field(
        default=DEFAULT_OPENAI_BASE_URL,
        description="API root; the engine appends /audio/transcriptions.",
    )
    language: str = Field(default="pt", description="Spoken language code; empty = auto.")
    prompt: str = Field(default="", description="Optional vocabulary/style hint.")
    timeout_seconds: float = Field(
        default=DEFAULT_OPENAI_TIMEOUT_SECONDS,
        gt=0,
        le=300,
        description="Network timeout for one transcription request.",
    )

    @field_validator("api_key")
    @classmethod
    def _strip_api_key(cls, value: str) -> str:
        return value.strip()

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model cannot be empty")
        return cleaned

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        if not cleaned:
            return DEFAULT_OPENAI_BASE_URL
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return cleaned

    @field_validator("language")
    @classmethod
    def _normalize_language(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("prompt")
    @classmethod
    def _strip_prompt(cls, value: str) -> str:
        return value.strip()


class GrammarSettings(BaseModel):
    """LanguageTool-based grammar/spelling correction options."""

    enabled: bool = True
    language: str = DEFAULT_GRAMMAR_LANGUAGE
    auto_download_java: bool = True
    max_matches: int = Field(default=5, ge=1, le=50)
    timeout_seconds: float = Field(default=15.0, gt=0)

    @field_validator("language")
    @classmethod
    def _normalize_language(cls, value: str) -> str:
        return value.strip()


class AudioSettings(BaseModel):
    """Microphone capture options."""

    sample_rate: int = Field(default=TARGET_SAMPLE_RATE, ge=8_000, le=48_000)
    channels: int = Field(default=AUDIO_CHANNELS, ge=1, le=2)
    device: str = Field(
        default="", description="Substring of device name or index; empty = default."
    )
    blocksize: int = Field(default=AUDIO_BLOCKSIZE, ge=128, le=8192)


class HotkeySettings(BaseModel):
    """Global hotkey behaviour."""

    mode: Literal["hold", "toggle"] = "hold"
    trigger: str = DEFAULT_HOTKEY_TRIGGER
    cloud_trigger: str = DEFAULT_HOTKEY_CLOUD_TRIGGER
    toggle_enabled: str = DEFAULT_HOTKEY_TOGGLE_ENABLED
    suppress: bool = Field(
        default=True,
        description="Swallow the hotkey so the focused app does not receive it.",
    )

    @field_validator("trigger", "cloud_trigger", "toggle_enabled")
    @classmethod
    def _validate_hotkey(cls, value: str) -> str:
        cleaned = value.strip().lower()
        # Split by +, then strip each part and filter empty
        parts = [p.strip() for p in cleaned.split("+") if p.strip()]
        if not parts:
            raise ValueError("hotkey cannot be empty")
        if len(parts) > 4:
            raise ValueError(f"hotkey '{value}' has too many keys")
        return "+".join(parts)

    @model_validator(mode="after")
    def _hotkeys_must_be_distinct(self) -> Self:
        seen: dict[str, str] = {}
        for field_name in ("trigger", "cloud_trigger", "toggle_enabled"):
            value = getattr(self, field_name)
            if value in seen:
                raise ValueError(
                    f"hotkeys must be different: '{field_name}' duplicates '{seen[value]}'"
                )
            seen[value] = field_name
        return self


class OverlaySettings(BaseModel):
    """On-screen indicator options."""

    enabled: bool = True
    position: Literal["top-center", "center", "bottom-center", "mouse"] = "bottom-center"
    always_show_on_success_ms: int = Field(default=1200, ge=0, le=10_000)


class InjectorSettings(BaseModel):
    """How final text is delivered to the focused window."""

    mode: Literal["paste", "type"] = "paste"
    restore_clipboard: bool = True
    fallback_to_type: bool = Field(
        default=True,
        description="Type the text directly when clipboard paste fails.",
    )
    char_interval_s: float = Field(default=0.001, ge=0.0, le=0.1)
    pre_inject_delay_s: float = Field(default=0.05, ge=0.0, le=1.0)


class StartupSettings(BaseModel):
    """Windows auto-start options."""

    auto_start: bool = False


# ---------------------------------------------------------------------------
# Root settings object
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Root settings — the single source of truth for runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="WHISPER_FREE_",
        env_nested_delimiter="__",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    version: str = APP_VERSION
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    single_instance: bool = True

    whisper: WhisperSettings = Field(default_factory=WhisperSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    grammar: GrammarSettings = Field(default_factory=GrammarSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    hotkey: HotkeySettings = Field(default_factory=HotkeySettings)
    overlay: OverlaySettings = Field(default_factory=OverlaySettings)
    injector: InjectorSettings = Field(default_factory=InjectorSettings)
    startup: StartupSettings = Field(default_factory=StartupSettings)


def load_settings(**overrides: object) -> Settings:
    """Build a :class:`Settings` instance, applying explicit overrides last."""
    settings = Settings()
    if overrides:
        return settings.model_copy(update=overrides)
    return settings
