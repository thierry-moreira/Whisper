"""Tests for the state machine transitions."""

from __future__ import annotations

import pytest

from whisper_free.core.states import (
    AppState,
    StateTransitionError,
    assert_transition,
    can_transition,
)


class TestAllowedTransitions:
    def test_idle_to_listening(self):
        assert can_transition(AppState.IDLE, AppState.LISTENING)

    def test_listening_to_processing(self):
        assert can_transition(AppState.LISTENING, AppState.PROCESSING)

    def test_processing_to_injecting(self):
        assert can_transition(AppState.PROCESSING, AppState.INJECTING)

    def test_injecting_to_idle(self):
        assert can_transition(AppState.INJECTING, AppState.IDLE)

    def test_idle_to_disabled(self):
        assert can_transition(AppState.IDLE, AppState.DISABLED)

    def test_disabled_to_idle(self):
        assert can_transition(AppState.DISABLED, AppState.IDLE)

    def test_listening_can_be_aborted_to_idle(self):
        assert can_transition(AppState.LISTENING, AppState.IDLE)

    def test_processing_can_recover_to_idle(self):
        assert can_transition(AppState.PROCESSING, AppState.IDLE)


class TestIllegalTransitions:
    def test_idle_cannot_jump_to_processing(self):
        assert not can_transition(AppState.IDLE, AppState.PROCESSING)

    def test_idle_cannot_jump_to_injecting(self):
        assert not can_transition(AppState.IDLE, AppState.INJECTING)

    def test_listening_cannot_jump_to_injecting(self):
        assert not can_transition(AppState.LISTENING, AppState.INJECTING)

    def test_disabled_cannot_listen(self):
        assert not can_transition(AppState.DISABLED, AppState.LISTENING)

    def test_assert_transition_raises(self):
        with pytest.raises(StateTransitionError):
            assert_transition(AppState.IDLE, AppState.INJECTING)

    def test_assert_transition_passes_when_legal(self):
        assert_transition(AppState.IDLE, AppState.LISTENING)  # must not raise


class TestProperties:
    def test_busy_states(self):
        assert AppState.LISTENING.is_busy()
        assert AppState.PROCESSING.is_busy()
        assert AppState.INJECTING.is_busy()

    def test_non_busy_states(self):
        assert not AppState.IDLE.is_busy()
        assert not AppState.DISABLED.is_busy()
