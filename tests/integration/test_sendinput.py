"""Integration tests that touch the real Windows desktop.

Run explicitly with ``pytest -m integration``.
"""

from __future__ import annotations

import pytest

from whisper_free.input.injector import _SendInputKeySender
from whisper_free.utils.helpers import is_windows

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not is_windows(), reason="SendInput only available on Windows"),
]


class TestRealSendInput:
    def test_instantiation(self):
        assert _SendInputKeySender() is not None

    def test_send_ctrl_v_does_not_crash(self):
        _SendInputKeySender().send_ctrl_v()
