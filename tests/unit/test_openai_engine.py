"""Tests for the OpenAI cloud transcription engine."""

from __future__ import annotations

import io
import urllib.error

import numpy as np
import pytest

from whisper_free.config.settings import Settings
from whisper_free.transcription.openai_engine import (
    OpenAIEngine,
    OpenAITranscriptionError,
    _build_multipart,
    encode_wav,
)


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.closed = False

    def read(self) -> bytes:
        return self._payload

    def close(self) -> None:
        self.closed = True


def make_settings() -> Settings:
    s = Settings()
    s.openai.api_key = "sk-test-key"
    s.openai.model = "gpt-4o-transcribe"
    s.openai.base_url = "https://api.example.com/v1"
    s.openai.language = "pt"
    s.audio.sample_rate = 16_000
    return s


class TestEncodeWav:
    def test_writes_pcm16_mono_wav(self, float_audio):
        data = encode_wav(float_audio, 16_000)

        assert data[:4] == b"RIFF"
        assert data[8:12] == b"WAVE"
        # header is 44 bytes for a standard PCM WAV
        assert len(data) == 44 + float_audio.size * 2

    def test_rejects_empty_audio(self):
        with pytest.raises(OpenAITranscriptionError):
            encode_wav(np.zeros(0, dtype=np.float32), 16_000)

    def test_flattens_stereo(self):
        stereo = np.zeros((100, 2), dtype=np.float32)
        stereo[:, 0] = 0.5
        data = encode_wav(stereo, 16_000)
        assert data[:4] == b"RIFF"


class TestBuildMultipart:
    def test_includes_fields_and_file(self):
        body, content_type = _build_multipart(
            {"model": "gpt-4o-transcribe", "response_format": "json"},
            b"WAVDATA",
        )
        assert content_type.startswith("multipart/form-data; boundary=")
        assert b'name="model"' in body
        assert b"gpt-4o-transcribe" in body
        assert b'name="file"; filename="audio.wav"' in body
        assert b"WAVDATA" in body
        assert body.endswith(b"--\r\n")

    def test_skips_empty_fields(self):
        body, _ = _build_multipart({"prompt": ""}, b"WAVDATA")
        assert b'name="prompt"' not in body


class TestOpenAIEngine:
    def test_is_configured(self):
        s = make_settings()
        assert OpenAIEngine(s).is_configured is True
        s.openai.api_key = ""
        assert OpenAIEngine(s).is_configured is False

    def test_transcribe_success(self, float_audio):
        captured = {}

        def opener(request, timeout=None):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.headers)
            captured["body"] = request.data
            captured["timeout"] = timeout
            return FakeResponse('{"text":"olá mundo"}'.encode())

        engine = OpenAIEngine(make_settings(), opener=opener)
        result = engine.transcribe(float_audio)

        assert result.text == "olá mundo"
        assert captured["url"] == "https://api.example.com/v1/audio/transcriptions"
        assert captured["headers"]["Authorization"] == "Bearer sk-test-key"
        assert captured["headers"]["Content-type"].startswith("multipart/form-data")
        assert b"gpt-4o-transcribe" in captured["body"]
        assert b'filename="audio.wav"' in captured["body"]

    def test_transcribe_without_key_raises(self, float_audio):
        s = make_settings()
        s.openai.api_key = ""
        engine = OpenAIEngine(s, opener=lambda *a, **k: FakeResponse(b"{}"))
        with pytest.raises(OpenAITranscriptionError) as excinfo:
            engine.transcribe(float_audio)
        assert "Chave da API OpenAI" in str(excinfo.value)

    def test_transcribe_disabled_raises(self, float_audio):
        s = make_settings()
        s.openai.enabled = False
        engine = OpenAIEngine(s, opener=lambda *a, **k: FakeResponse(b"{}"))
        with pytest.raises(OpenAITranscriptionError):
            engine.transcribe(float_audio)

    def test_http_401_friendly_error(self, float_audio):
        def opener(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"error":{"message":"bad key sk-abcdefgh"}}'),
            )

        engine = OpenAIEngine(make_settings(), opener=opener)
        with pytest.raises(OpenAITranscriptionError) as excinfo:
            engine.transcribe(float_audio)
        message = str(excinfo.value)
        assert "Chave da API OpenAI inválida" in message
        assert "sk-abcdefgh" not in message

    def test_network_error(self, float_audio):
        def opener(request, timeout=None):
            raise urllib.error.URLError("offline")

        engine = OpenAIEngine(make_settings(), opener=opener)
        with pytest.raises(OpenAITranscriptionError) as excinfo:
            engine.transcribe(float_audio)
        assert "Não foi possível conectar" in str(excinfo.value)

    def test_timeout(self, float_audio):
        def opener(request, timeout=None):
            raise TimeoutError

        engine = OpenAIEngine(make_settings(), opener=opener)
        with pytest.raises(OpenAITranscriptionError):
            engine.transcribe(float_audio)
