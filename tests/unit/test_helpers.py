"""Tests for the small helper utilities."""

from __future__ import annotations

from whisper_free.utils.helpers import AtomicFlag, clamp, is_windows


class TestPlatformHelpers:
    def test_is_windows_matches_platform(self):
        import sys

        assert is_windows() == sys.platform.startswith("win")


class TestClamp:
    def test_within_range(self):
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_range(self):
        assert clamp(-1.0, 0.0, 10.0) == 0.0

    def test_above_range(self):
        assert clamp(11.0, 0.0, 10.0) == 10.0

    def test_boundaries_inclusive(self):
        assert clamp(0.0, 0.0, 10.0) == 0.0
        assert clamp(10.0, 0.0, 10.0) == 10.0


class TestAtomicFlag:
    def test_initial_value(self):
        assert AtomicFlag().get() is False
        assert AtomicFlag(True).get() is True

    def test_set_and_get(self):
        flag = AtomicFlag()
        flag.set(True)
        assert flag.get() is True
        assert bool(flag) is True
        flag.set(False)
        assert flag.get() is False
