"""Tests for the whisper model factory and the CUDA -> CPU fallback."""

from __future__ import annotations

import sys
import types
from typing import ClassVar

import numpy as np
import pytest

from whisper_free.core.gpu_manager import GPUManager, _Factories
from whisper_free.transcription import whisper_engine
from whisper_free.transcription.whisper_engine import WhisperEngine, create_whisper_model


def _install_fake_module(monkeypatch, model_cls) -> None:
    module = types.ModuleType("faster_whisper")
    module.WhisperModel = model_cls
    monkeypatch.setitem(sys.modules, "faster_whisper", module)


class RecordingModel:
    calls: ClassVar[list[tuple[str, str]]] = []
    fail_cuda = False

    def __init__(self, name, device, compute_type, cpu_threads, download_root):
        type(self).calls.append((device, compute_type))
        if device == "cuda" and type(self).fail_cuda:
            raise RuntimeError("CUDA driver version is insufficient for CUDA runtime version")
        self.device = device
        self.compute_type = compute_type


@pytest.fixture(autouse=True)
def _reset_recording_model():
    RecordingModel.calls = []
    RecordingModel.fail_cuda = False
    yield
    RecordingModel.calls = []
    RecordingModel.fail_cuda = False


class TestCreateWhisperModel:
    def test_cuda_failure_falls_back_to_cpu(self, settings, monkeypatch):
        settings.whisper.device = "cuda"
        settings.whisper.compute_type = "int8_float16"
        settings.whisper.fallback_to_cpu = True
        RecordingModel.fail_cuda = True
        monkeypatch.setattr(whisper_engine, "_cuda_runtime_available", lambda: True)
        _install_fake_module(monkeypatch, RecordingModel)

        model = create_whisper_model(settings)

        assert RecordingModel.calls == [("cuda", "int8_float16"), ("cpu", "int8")]
        assert model.device == "cpu"

    def test_fallback_can_be_disabled(self, settings, monkeypatch):
        settings.whisper.device = "cuda"
        settings.whisper.compute_type = "int8_float16"
        settings.whisper.fallback_to_cpu = False
        RecordingModel.fail_cuda = True
        monkeypatch.setattr(whisper_engine, "_cuda_runtime_available", lambda: True)
        _install_fake_module(monkeypatch, RecordingModel)

        with pytest.raises(RuntimeError, match="CUDA"):
            create_whisper_model(settings)

        assert RecordingModel.calls == [("cuda", "int8_float16")]

    def test_non_cuda_failure_is_not_retried(self, settings, monkeypatch):
        class Broken:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("Unable to open model.bin")

        _install_fake_module(monkeypatch, Broken)

        with pytest.raises(RuntimeError, match=r"model\.bin"):
            create_whisper_model(settings)

    def test_cpu_with_float16_compute_type_uses_int8(self, settings, monkeypatch):
        settings.whisper.device = "cpu"
        settings.whisper.compute_type = "int8_float16"
        _install_fake_module(monkeypatch, RecordingModel)

        create_whisper_model(settings)

        assert RecordingModel.calls == [("cpu", "int8")]

    def test_auto_without_cuda_uses_cpu(self, settings, monkeypatch):
        settings.whisper.device = "auto"
        monkeypatch.setattr(whisper_engine, "_cuda_available", lambda: False)
        _install_fake_module(monkeypatch, RecordingModel)

        create_whisper_model(settings)

        assert RecordingModel.calls == [("cpu", "int8")]

    def test_missing_cublas_falls_back_to_cpu(self, settings, monkeypatch):
        settings.whisper.device = "cuda"
        settings.whisper.compute_type = "int8_float16"
        settings.whisper.fallback_to_cpu = True
        monkeypatch.setattr(whisper_engine, "_cuda_runtime_available", lambda: False)
        _install_fake_module(monkeypatch, RecordingModel)

        model = create_whisper_model(settings)

        assert RecordingModel.calls == [("cpu", "int8")]
        assert model.device == "cpu"

    def test_missing_cublas_without_fallback_raises(self, settings, monkeypatch):
        settings.whisper.device = "cuda"
        settings.whisper.fallback_to_cpu = False
        monkeypatch.setattr(whisper_engine, "_cuda_runtime_available", lambda: False)
        _install_fake_module(monkeypatch, RecordingModel)

        with pytest.raises(RuntimeError, match="CUDA runtime libraries are missing"):
            create_whisper_model(settings)

        assert RecordingModel.calls == []

    def test_force_cpu_overrides_cuda_setting(self, settings, monkeypatch):
        settings.whisper.device = "cuda"
        settings.whisper.compute_type = "int8_float16"
        monkeypatch.setattr(whisper_engine, "_cuda_runtime_available", lambda: True)
        _install_fake_module(monkeypatch, RecordingModel)

        model = create_whisper_model(settings, force_cpu=True)

        assert RecordingModel.calls == [("cpu", "int8")]
        assert model.device == "cpu"


class RuntimeCudaModel:
    device = "cuda"

    def transcribe(self, audio, **kwargs):
        raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")


class CpuModel:
    device = "cpu"

    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, audio, **kwargs):
        self.calls += 1
        info = types.SimpleNamespace(language="pt", language_probability=1.0, duration=0.5)
        segments = [types.SimpleNamespace(start=0.0, end=0.5, text=" Olá mundo.")]
        return iter(segments), info


class TestRuntimeFallback:
    def test_cuda_transcription_failure_retries_on_cpu(self, settings):
        settings.whisper.device = "cuda"
        settings.whisper.fallback_to_cpu = True
        cpu_model = CpuModel()
        gpu = GPUManager(
            settings,
            _Factories(
                whisper_factory=RuntimeCudaModel,
                whisper_cpu_factory=lambda: cpu_model,
            ),
        )
        engine = WhisperEngine(settings, gpu)

        result = engine.transcribe(np.zeros(8_000, dtype=np.float32))

        assert result.text == "Olá mundo."
        assert cpu_model.calls == 1
        assert gpu.whisper is cpu_model
        assert gpu.stats.device == "cpu"

    def test_cuda_transcription_failure_without_fallback_raises(self, settings):
        settings.whisper.device = "cuda"
        settings.whisper.fallback_to_cpu = False
        gpu = GPUManager(settings, _Factories(whisper_factory=RuntimeCudaModel))
        engine = WhisperEngine(settings, gpu)

        with pytest.raises(RuntimeError, match="cublas"):
            engine.transcribe(np.zeros(8_000, dtype=np.float32))

    def test_non_cuda_transcription_failure_is_not_retried(self, settings):
        settings.whisper.device = "cpu"
        settings.whisper.fallback_to_cpu = True

        class BrokenCpuModel:
            device = "cpu"

            def transcribe(self, audio, **kwargs):
                raise RuntimeError("Unable to open model.bin")

        gpu = GPUManager(settings, _Factories(whisper_factory=BrokenCpuModel))
        engine = WhisperEngine(settings, gpu)

        with pytest.raises(RuntimeError, match=r"model\.bin"):
            engine.transcribe(np.zeros(8_000, dtype=np.float32))
