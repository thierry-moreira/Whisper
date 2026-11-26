"""Tests for cloud/local mode dispatch in the transcription pipeline."""

from __future__ import annotations

from whisper_free.transcription.grammar import GrammarResult
from whisper_free.transcription.pipeline import TranscriptionMode, TranscriptionPipeline
from whisper_free.transcription.whisper_engine import TranscriptionResult


class FakeWhisper:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio):
        self.calls += 1
        return TranscriptionResult(text="texto local", language="pt")


class FakeOpenAI:
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio):
        self.calls += 1
        return TranscriptionResult(text="texto cloud", language="pt")


class FakeGrammar:
    def correct(self, text: str) -> GrammarResult:
        return GrammarResult(original=text, corrected=text)


class FakeGPU:
    def __init__(self) -> None:
        self.begins = 0
        self.ends = 0

    def begin_use(self) -> None:
        self.begins += 1

    def end_use(self) -> None:
        self.ends += 1


def make_pipeline(settings, openai_engine=None):
    whisper = FakeWhisper()
    grammar = FakeGrammar()
    gpu = FakeGPU()
    pipeline = TranscriptionPipeline(settings, whisper, grammar, gpu, openai_engine)
    return pipeline, whisper, grammar, gpu


def test_local_mode_uses_whisper_and_gpu(settings, float_audio):
    pipeline, whisper, _, gpu = make_pipeline(settings)

    result = pipeline.process(float_audio, mode=TranscriptionMode.LOCAL)

    assert result.mode is TranscriptionMode.LOCAL
    assert result.final_text == "Texto local"
    assert whisper.calls == 1
    assert gpu.begins == 1
    assert gpu.ends == 1


def test_cloud_mode_uses_openai_and_skips_gpu(settings, float_audio):
    openai = FakeOpenAI()
    pipeline, whisper, _, gpu = make_pipeline(settings, openai)

    result = pipeline.process(float_audio, mode=TranscriptionMode.CLOUD)

    assert result.mode is TranscriptionMode.CLOUD
    assert result.final_text == "Texto cloud"
    assert whisper.calls == 0
    assert openai.calls == 1
    assert gpu.begins == 0
    assert gpu.ends == 0


def test_cloud_mode_accepts_string(settings, float_audio):
    openai = FakeOpenAI()
    pipeline, _, _, _ = make_pipeline(settings, openai)

    result = pipeline.process(float_audio, mode="cloud")

    assert result.mode is TranscriptionMode.CLOUD
    assert openai.calls == 1


def test_cloud_mode_without_engine_reports_error(settings, float_audio):
    pipeline, _, _, _ = make_pipeline(settings, openai_engine=None)

    result = pipeline.process(float_audio, mode=TranscriptionMode.CLOUD)

    assert result.error is not None
    assert "OpenAI" in result.error
