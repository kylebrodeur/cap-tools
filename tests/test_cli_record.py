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


def test_record_forwards_window_id_to_run_beat(tmp_path):
    fake_result = BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "full.cap"),
        events=[], zoom_segments=[], export_path=None,
    )
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("capt.record.beat.run_beat", return_value=fake_result) as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path),
                                       "--window", "683", "--json"])

    assert result.exit_code == 0
    assert run_beat_mock.call_args.kwargs.get("window_id") == "683"


def test_record_rejects_screen_and_window_together(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path),
                                   "--screen", "1", "--window", "683"])

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_record_uses_powershell_hop_when_wsl(tmp_path):
    # The Windows side reports a BeatResult as snake_case JSON (asdict of
    # BeatResult); the --json output must be remapped into the SAME
    # camelCase/"type" schema the in-process (macOS/Linux) path emits, so a
    # --json consumer sees one shape regardless of platform.
    windows_result = json.dumps({
        "recording_id": "rec-1",
        "cap_path": "full.cap",
        "events": [],
        "zoom_segments": [],
        "export_path": None,
    })
    fake_proc = MagicMock(returncode=0, stdout=windows_result + "\n")
    with patch("capt.cli._is_wsl", return_value=True), \
         patch("subprocess.run", return_value=fake_proc) as run_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path), "--json"])

    assert result.exit_code == 0
    run_mock.assert_called_once()
    assert "powershell.exe" in run_mock.call_args[0][0]

    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["type"] == "Completed"
    assert payload["recordingId"] == "rec-1"
    assert payload["capPath"] == "full.cap"
    assert payload["zoomSegments"] == []
    assert payload["exportPath"] is None
    assert "recording_id" not in payload
    assert "cap_path" not in payload
    assert "status" not in payload


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
    assert called_steps == [{"action": "click", "selector": "#go"}]


def test_record_forwards_steps_marker_source_export_to_over_powershell(tmp_path):
    steps_file = tmp_path / "steps.json"
    steps_file.write_text(json.dumps([{"action": "click", "selector": "#go"}]))
    export_path = str(tmp_path / "out.mp4")
    fake_proc = MagicMock(returncode=0, stdout='{"recordingId": "rec-1", "cap_path": "full.cap"}\n')
    with patch("capt.cli._is_wsl", return_value=True), \
         patch("subprocess.run", return_value=fake_proc) as run_mock:
        runner = CliRunner()
        result = runner.invoke(main, [
            "record", "https://example.com", "--out", str(tmp_path),
            "--steps", str(steps_file),
            "--marker-source", "global-capture",
            "--export-to", export_path,
            "--json",
        ])

    assert result.exit_code == 0
    run_mock.assert_called_once()
    ps_cmd = run_mock.call_args[0][0][3]
    assert f"--steps {steps_file}" in ps_cmd
    assert "--marker-source global-capture" in ps_cmd
    assert f"--export-to {export_path}" in ps_cmd


def test_record_non_json_output_uses_cap_path_from_windows_result(tmp_path):
    fake_proc = MagicMock(returncode=0, stdout='{"recordingId": "rec-1", "cap_path": "full.cap"}\n')
    with patch("capt.cli._is_wsl", return_value=True), \
         patch("subprocess.run", return_value=fake_proc):
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path)])

    assert result.exit_code == 0
    assert "full.cap" in result.output
    assert "capProjectPath" not in result.output


def test_record_forwards_storage_state_to_run_beat(tmp_path):
    fake_result = BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "full.cap"),
        events=[], zoom_segments=[], export_path=None,
    )
    state_file = tmp_path / "state.json"
    state_file.write_text("{}")
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("capt.record.beat.run_beat", return_value=fake_result) as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path),
                                       "--storage-state", str(state_file), "--json"])

    assert result.exit_code == 0
    assert run_beat_mock.call_args.kwargs.get("storage_state") == str(state_file)
    assert run_beat_mock.call_args.kwargs.get("user_data_dir") is None


def test_record_forwards_user_data_dir_to_run_beat(tmp_path):
    fake_result = BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "full.cap"),
        events=[], zoom_segments=[], export_path=None,
    )
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("capt.record.beat.run_beat", return_value=fake_result) as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path),
                                       "--user-data-dir", str(profile_dir), "--json"])

    assert result.exit_code == 0
    assert run_beat_mock.call_args.kwargs.get("user_data_dir") == str(profile_dir)


def test_record_pick_selects_window_from_targets(tmp_path):
    fake_result = BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "full.cap"),
        events=[], zoom_segments=[], export_path=None,
    )
    fake_targets = {
        "screens": [{"id": "1", "name": "Main", "primary": True}],
        "windows": [
            {"id": "8782", "name": "ReelBinder", "ownerName": "ReelBinder"},
            {"id": "103", "name": "Term", "ownerName": "Tabby"},
        ],
    }
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("capt.record.beat.run_beat", return_value=fake_result) as run_beat_mock, \
         patch("capt.targets.list_targets", return_value=fake_targets):
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path),
                                       "--pick", "--json"], input="1\n")

    assert result.exit_code == 0, result.output
    assert run_beat_mock.call_args.kwargs.get("window_id") == "8782"
    assert run_beat_mock.call_args.kwargs.get("screen_id") is None


def test_record_pick_rejects_screen_and_window_together():
    runner = CliRunner()
    result = runner.invoke(main, ["record", "--pick", "--screen", "1", "--window", "8782"])

    assert result.exit_code != 0
    assert "cannot be combined" in result.output


def test_pick_target_returns_none_without_targets():
    from capt.cli import _pick_target

    with patch("capt.targets.list_targets", return_value=None):
        assert _pick_target() is None

def test_record_pick_rejects_screen_and_window_together():
    runner = CliRunner()
    result = runner.invoke(main, ["record", "--pick", "--screen", "1", "--window", "8782"])

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_pick_target_lists_windows_then_screens():
    from capt import cli

    fake_targets = {
        "screens": [{"id": "1", "name": "Built-in Display"}],
        "windows": [{"id": "8782", "name": "ReelBinder", "ownerName": "ReelBinder"}],
    }
    with patch("capt.targets.list_targets", return_value=fake_targets), \
         patch.object(cli.click, "prompt", return_value=1):
        assert cli._pick_target() == ("window", "8782")
