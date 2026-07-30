from unittest.mock import MagicMock, patch

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
