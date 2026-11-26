"""Tests for GPUManager lazy loading, idle unload and use tracking."""

from __future__ import annotations

import time

from whisper_free.core.gpu_manager import GPUManager, _Factories


class FakeModel:
    device = "cuda"


def _manager(settings):
    calls = []

    def factory():
        calls.append(1)
        return FakeModel()

    return GPUManager(settings, _Factories(whisper_factory=factory)), calls


class TestLazyLoading:
    def test_loads_only_on_demand_and_once(self, settings):
        gpu, calls = _manager(settings)

        assert gpu.whisper is None
        assert calls == []

        gpu.ensure_loaded()
        gpu.ensure_loaded()

        assert calls == [1]
        assert gpu.stats.loaded is True
        assert gpu.stats.device == "cuda"
        assert gpu.stats.whisper_model == settings.whisper.model_size

    def test_stats_snapshot_is_a_copy(self, settings):
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()

        snapshot = gpu.stats
        gpu.unload_models(force=True)

        assert snapshot.loaded is True
        assert gpu.stats.loaded is False


class TestUnload:
    def test_unload_clears_models_and_stats(self, settings):
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()

        gpu.unload_models()

        assert gpu.whisper is None
        assert gpu.stats.loaded is False
        assert gpu.stats.whisper_model == ""

    def test_unload_is_deferred_during_use(self, settings):
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()
        gpu.begin_use()

        gpu.unload_models()
        assert gpu.whisper is not None

        gpu.end_use()
        assert gpu.whisper is None

    def test_force_unload_during_use(self, settings):
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()
        gpu.begin_use()

        gpu.unload_models(force=True)
        assert gpu.whisper is None

        gpu.end_use()  # must not resurrect the model or crash


class TestIdleUnload:
    def test_idle_timeout_unloads(self, settings):
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()
        gpu._last_used = time.monotonic() - (settings.whisper.idle_unload_seconds + 5)

        gpu._idle_unload()

        assert gpu.whisper is None

    def test_recent_use_rearms_the_timer(self, settings):
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()
        gpu._last_used = time.monotonic()

        gpu._idle_unload()

        assert gpu.whisper is not None
        assert gpu._idle_timer is not None
        gpu.unload_models(force=True)  # cancels the pending timer

    def test_end_use_unloads_immediately_by_default(self, settings):
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()
        gpu.begin_use()

        gpu.end_use()

        assert gpu.whisper is None
        assert gpu._idle_timer is None

    def test_end_use_schedules_timer_when_keep_warm(self, settings):
        settings.whisper.unload_after_use = False
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()
        gpu.begin_use()

        gpu.end_use()

        assert gpu.whisper is not None
        assert gpu._idle_timer is not None
        gpu.unload_models(force=True)

    def test_zero_disables_idle_unload(self, settings):
        settings.whisper.unload_after_use = False
        settings.whisper.idle_unload_seconds = 0
        gpu, _ = _manager(settings)
        gpu.ensure_loaded()
        gpu.begin_use()

        gpu.end_use()

        assert gpu._idle_timer is None
