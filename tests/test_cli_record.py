import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from capt.cli import main
from capt.record.beat import BeatResult


def test_record_calls_run_beat_in_process_when_not_wsl(tmp_path):
    fake_result = BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "full.cap"),
        events=[], zoom_segments=[], export_path=None,
    )
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("capt.record.beat.run_beat", return_value=fake_result) as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path), "--json"])

    assert result.exit_code == 0
    run_beat_mock.assert_called_once()
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["recordingId"] == "rec-1"
    assert payload["capPath"] == str(tmp_path / "full.cap")


def test_record_uses_powershell_hop_when_wsl(tmp_path):
    fake_proc = MagicMock(returncode=0, stdout='{"recordingId": "rec-1", "capProjectPath": "full.cap"}\n')
    with patch("capt.cli._is_wsl", return_value=True), \
         patch("subprocess.run", return_value=fake_proc) as run_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path), "--json"])

    assert result.exit_code == 0
    run_mock.assert_called_once()
    assert "powershell.exe" in run_mock.call_args[0][0]


def test_record_reads_steps_json_file(tmp_path):
    steps_file = tmp_path / "steps.json"
    steps_file.write_text(json.dumps([{"action": "click", "selector": "#go"}]))
    fake_result = BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "full.cap"),
        events=[], zoom_segments=[], export_path=None,
    )
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("capt.record.beat.run_beat", return_value=fake_result) as run_beat_mock:
        runner = CliRunner()
        runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path),
                             "--steps", str(steps_file)])

    called_steps = run_beat_mock.call_args.kwargs.get("steps", run_beat_mock.call_args[0][1] if len(run_beat_mock.call_args[0]) > 1 else None)
