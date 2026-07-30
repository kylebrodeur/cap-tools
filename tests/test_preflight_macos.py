import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only module")

from unittest.mock import MagicMock, patch

from capt.preflight_macos import gate_global_capture_permission


def test_gate_global_capture_permission_false_without_input_monitoring():
    # Real, not mocked — this terminal has not been granted Input Monitoring.
    passed, message = gate_global_capture_permission()
    assert passed is False
    assert "Input Monitoring" in message


def test_gate_global_capture_permission_true_when_capture_starts_cleanly():
    fake_capture = MagicMock()
    with patch("capt.preflight_macos.GlobalCapture", return_value=fake_capture):
        passed, message = gate_global_capture_permission()
    assert passed is True
    fake_capture.start.assert_called_once()
    fake_capture.stop.assert_called_once()
