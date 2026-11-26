"""OpenAI cloud transcription engine.

Sends a 16-bit PCM WAV to ``POST {base_url}/audio/transcriptions`` using only
the standard library (``urllib`` + ``wave``), so no extra dependency is needed.

The API key is never logged.  HTTP failures are translated into short,
user-facing Portuguese messages that the overlay can display directly.
"""

from __future__ import annotations

import io
import json
import re
import time
import urllib.error
import urllib.request
import uuid
import wave
from collections.abc import Callable
from typing import Any

import numpy as np

from whisper_free.config import constants
from whisper_free.config.settings import Settings
from whisper_free.transcription.whisper_engine import TranscriptionResult
from whisper_free.utils.logging import get_logger

logger = get_logger("whisper_free.openai")

_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


class OpenAITranscriptionError(RuntimeError):
    """Raised when the OpenAI transcription request cannot be completed."""


class OpenAIEngine:
    """Thin, synchronous client for the OpenAI audio transcription endpoint."""

    def __init__(
        self,
        settings: Settings,
        *,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings
        self._opener = opener or urllib.request.urlopen

    @property
    def is_configured(self) -> bool:
        config = self._settings.openai
        return bool(config.enabled and config.api_key.strip())

    def transcribe(self, audio: np.ndarray) -> TranscriptionResult:
        """Transcribe *audio* (float32 mono) through the OpenAI API."""
        config = self._settings.openai
        if not config.enabled:
            raise OpenAITranscriptionError("Transcrição via API está desativada.")
        if not config.api_key.strip():
            raise OpenAITranscriptionError(
                "Chave da API OpenAI não configurada. Abra o menu do tray e escolha "
                "“Configurar API OpenAI”."
            )

        started = time.perf_counter()
        wav_bytes = encode_wav(audio, self._settings.audio.sample_rate)
        if len(wav_bytes) > constants.OPENAI_MAX_UPLOAD_BYTES:
            raise OpenAITranscriptionError("Áudio muito longo para a API OpenAI (limite de 25 MB).")

        fields = {"model": config.model, "response_format": "json"}
        if config.language:
            fields["language"] = config.language
        if config.prompt:
            fields["prompt"] = config.prompt
        body, content_type = _build_multipart(fields, wav_bytes)
        url = f"{config.base_url}/audio/transcriptions"
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": content_type,
                "Accept": "application/json",
                "User-Agent": f"{constants.APP_NAME}/{constants.APP_VERSION}",
            },
        )

        logger.info(
            "OpenAI transcription started (model='{}', audio={:.2f}s, {:.1f} KB)",
            config.model,
            _duration_s(audio, self._settings.audio.sample_rate),
            len(wav_bytes) / 1024,
        )
        try:
            response = self._opener(request, timeout=config.timeout_seconds)
            try:
                payload = response.read()
            finally:
                close = getattr(response, "close", None)
                if close is not None:
                    close()
        except urllib.error.HTTPError as exc:
            detail = _read_http_error(exc)
            logger.warning("OpenAI HTTP {}: {}", exc.code, detail)
            raise OpenAITranscriptionError(_friendly_http_error(exc.code, detail)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning(f"OpenAI request failed: {exc}")
            raise OpenAITranscriptionError(
                "Não foi possível conectar à OpenAI. Verifique a internet e tente novamente."
            ) from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"OpenAI request failed: {exc}")
            raise OpenAITranscriptionError(f"Falha na API OpenAI: {exc}") from exc

        text = _extract_text(payload)
        elapsed = time.perf_counter() - started
        logger.info(
            "OpenAI transcription finished in {:.2f}s -> '{}'",
            elapsed,
            _preview(text),
        )
        return TranscriptionResult(
            text=text,
            language=config.language,
            duration_s=_duration_s(audio, self._settings.audio.sample_rate),
            elapsed_s=elapsed,
        )


def encode_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert a float32 mono signal in [-1, 1] to 16-bit PCM WAV bytes."""
    samples = np.asarray(audio)
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    samples = samples.reshape(-1)
    if samples.size == 0:
        raise OpenAITranscriptionError("Nenhum áudio para enviar à API.")
    if samples.dtype == np.int16:
        samples = samples.astype(np.float32) / 32768.0
    else:
        samples = samples.astype(np.float32)
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767.0).astype("<i2")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _build_multipart(
    fields: dict[str, str],
    file_bytes: bytes,
    *,
    filename: str = "audio.wav",
    file_content_type: str = "audio/wav",
) -> tuple[bytes, str]:
    """Build a multipart/form-data body without external dependencies."""
    boundary = f"----WhisperFree{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        if value == "":
            continue
        chunks.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()
        )
    chunks.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {file_content_type}\r\n\r\n"
        ).encode()
    )
    chunks.append(file_bytes)
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        if isinstance(data, dict):
            error = data.get("error")
            message = error.get("message") if isinstance(error, dict) else data.get("message")
            if message:
                return _redact(str(message).strip())
        return _redact(body.strip())[:240]
    except Exception:
        return ""


def _friendly_http_error(status: int, detail: str) -> str:
    if status == 401:
        return "Chave da API OpenAI inválida ou revogada (HTTP 401)."
    if status == 403:
        return "Acesso negado pela OpenAI (HTTP 403). Verifique a chave e o projeto."
    if status == 404:
        return "Modelo ou endpoint não encontrado (HTTP 404). Verifique o modelo configurado."
    if status == 413:
        return "Áudio muito longo para a API OpenAI (HTTP 413)."
    if status == 429:
        return "Limite de uso da OpenAI atingido (HTTP 429). Tente novamente em instantes."
    if status >= 500:
        return f"A OpenAI está indisponível no momento (HTTP {status}). Tente novamente."
    suffix = f": {detail}" if detail else ""
    return f"Falha na API OpenAI (HTTP {status}){suffix}"


def _extract_text(payload: bytes | str) -> str:
    if isinstance(payload, bytes):
        text_payload = payload.decode("utf-8", errors="replace")
    else:
        text_payload = payload
    stripped = text_payload.strip()
    if not stripped:
        return ""
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    if isinstance(data, dict):
        text = data.get("text", "")
        return str(text).strip()
    return stripped


def _duration_s(audio: np.ndarray, sample_rate: int) -> float:
    samples = np.asarray(audio)
    count = samples.shape[0] if samples.ndim else 0
    return count / sample_rate if sample_rate else 0.0


def _redact(text: str) -> str:
    return _KEY_PATTERN.sub("sk-***", text)


def _preview(text: str, limit: int = 100) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
