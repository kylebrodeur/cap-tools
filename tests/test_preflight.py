from unittest.mock import MagicMock, patch

from capt.preflight import _cap_json
from capt.preflight_windows import gate_powershell_reachable


def test_gate_powershell_reachable_true_when_echo_succeeds():
    fake_proc = MagicMock(stdout="ok\n")
    with patch("subprocess.run", return_value=fake_proc):
        passed, message = gate_powershell_reachable()
    assert passed is True
    assert "PowerShell reachable" in message


def test_gate_powershell_reachable_false_on_exception():
    with patch("subprocess.run", side_effect=FileNotFoundError("no powershell.exe")):
        passed, message = gate_powershell_reachable()
    assert passed is False
    assert "NOT reachable" in message


def test_cap_json_returns_none_when_cap_binary_missing():
    # Regression test: preflight() calls _cap_json("targets") unconditionally
    # even when G1 already found cap-cli missing. Without this, a bare
    # FileNotFoundError from subprocess.run crashed the whole preflight run
    # instead of letting G2 report "no screen targets found".
    with patch("subprocess.run", side_effect=FileNotFoundError("no cap")):
        result = _cap_json("targets")
    assert result is None
