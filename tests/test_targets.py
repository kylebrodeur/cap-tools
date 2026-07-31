import subprocess
from unittest.mock import MagicMock, patch

from capt.targets import default_mic_name, default_screen_id, list_targets


def test_list_targets_returns_parsed_json_on_success():
    fake_proc = MagicMock(returncode=0, stdout='{"screens": [{"id": "1"}]}')
    with patch("subprocess.run", return_value=fake_proc):
        result = list_targets()
    assert result == {"screens": [{"id": "1"}]}


def test_list_targets_returns_none_when_cap_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError("no cap")):
        assert list_targets() is None


def test_list_targets_returns_none_on_nonzero_exit():
    fake_proc = MagicMock(returncode=1, stdout="")
    with patch("subprocess.run", return_value=fake_proc):
        assert list_targets() is None


def test_list_targets_returns_none_on_unparseable_output():
    fake_proc = MagicMock(returncode=0, stdout="not json")
    with patch("subprocess.run", return_value=fake_proc):
        assert list_targets() is None


def test_list_targets_returns_none_on_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="cap", timeout=30)):
        assert list_targets() is None


def test_default_screen_id_prefers_primary():
    targets = {"screens": [{"id": "1", "primary": False}, {"id": "2", "primary": True}]}
    assert default_screen_id(targets) == "2"


def test_default_screen_id_falls_back_to_first_when_none_primary():
    targets = {"screens": [{"id": "1", "primary": False}, {"id": "2", "primary": False}]}
    assert default_screen_id(targets) == "1"


def test_default_screen_id_none_when_no_screens():
    assert default_screen_id({"screens": []}) is None


def test_default_mic_name_returns_first_mic():
    targets = {"mics": [{"name": "MacBook Pro Microphone"}, {"name": "Other Mic"}]}
    assert default_mic_name(targets) == "MacBook Pro Microphone"


def test_default_mic_name_none_when_no_mics():
    assert default_mic_name({"mics": []}) is None
