"""Tests for the synchronous transcription pipeline."""

from __future__ import annotations

import pytest

from whisper_free.transcription.grammar import GrammarResult
from whisper_free.transcription.pipeline import TranscriptionPipeline
from whisper_free.transcription.whisper_engine import TranscriptionResult


class FakeWhisper:
    def __init__(self, text: str = "olá mundo") -> None:
        self.text = text
        self.error: str | None = None
        self.calls = 0
        self.warmups = 0

    def transcribe(self, audio):
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return TranscriptionResult(text=self.text, language="pt")

    def warmup(self) -> None:
        self.warmups += 1


class FakeGrammar:
    def __init__(self, corrected: str | None = None) -> None:
        self.corrected = corrected
        self.warmups = 0
        self.closed = False

    def correct(self, text: str) -> GrammarResult:
        return GrammarResult(original=text, corrected=self.corrected or text)

    def warmup(self) -> None:
        self.warmups += 1

    def close(self) -> None:
        self.closed = True


class FakeGPU:
    def __init__(self) -> None:
        self.begins = 0
        self.ends = 0
        self.unloads: list[bool] = []
        self.touches = 0

    def begin_use(self) -> None:
        self.begins += 1

    def end_use(self) -> None:
        self.ends += 1

    def unload_models(self, *, force: bool = False) -> None:
        self.unloads.append(force)

    def touch(self) -> None:
        self.touches += 1


@pytest.fixture
def pipeline(settings):
    whisper = FakeWhisper()
    grammar = FakeGrammar()
    gpu = FakeGPU()
    return TranscriptionPipeline(settings, whisper, grammar, gpu), whisper, grammar, gpu


def test_process_marks_gpu_use(pipeline, float_audio):
    pipe, whisper, _, gpu = pipeline

    result = pipe.process(float_audio)

    assert result.ok
    assert result.final_text == "Olá mundo"
    assert whisper.calls == 1
    assert gpu.begins == 1
    assert gpu.ends == 1


def test_process_releases_use_on_exception(pipeline, float_audio):
    pipe, whisper, _, gpu = pipeline
    whisper.error = "boom"

    result = pipe.process(float_audio)

    assert result.error == "boom"
    assert gpu.begins == 1
    assert gpu.ends == 1


def test_process_empty_transcription_returns_empty(pipeline, float_audio):
    pipe, whisper, _, gpu = pipeline
    whisper.text = ""

    result = pipe.process(float_audio)

    assert result.final_text == ""
    assert gpu.begins == 1
    assert gpu.ends == 1


def test_prepare_grammar_warms_up(settings, pipeline):
    settings.grammar.enabled = True
    pipe, _, grammar, _ = pipeline

    pipe.prepare_grammar()

    assert grammar.warmups == 1


def test_prepare_grammar_skipped_when_disabled(settings):
    settings.grammar.enabled = False
    grammar = FakeGrammar()
    pipe = TranscriptionPipeline(settings, FakeWhisper(), grammar, FakeGPU())

    pipe.prepare_grammar()

    assert grammar.warmups == 0


def test_shutdown_forces_unload(pipeline):
    pipe, _, grammar, gpu = pipeline

    pipe.shutdown()

    assert grammar.closed is True
    assert gpu.unloads == [True]


def test_warmup_touches_gpu(pipeline):
    pipe, whisper, _, gpu = pipeline

    pipe.warmup()

    assert whisper.warmups == 1
    assert gpu.touches == 1
