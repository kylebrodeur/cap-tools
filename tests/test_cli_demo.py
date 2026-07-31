from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from capt.cli import main
from capt.record.beat import BeatResult

FAKE_TARGETS = {
    "screens": [{"id": "1", "primary": True}],
    "mics": [{"name": "MacBook Pro Microphone"}],
}


def _fake_result(tmp_path):
    return BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "my-demo.cap"),
        events=[], zoom_segments=[], export_path=str(tmp_path / "my-demo.mp4"),
    )


def test_demo_auto_detects_screen_and_mic(tmp_path):
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("sys.platform", "darwin"), \
         patch("capt.preflight.preflight", return_value=True), \
         patch("capt.targets.list_targets", return_value=FAKE_TARGETS), \
         patch("capt.record.beat.run_beat", return_value=_fake_result(tmp_path)) as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "my-demo", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    kwargs = run_beat_mock.call_args.kwargs
    assert kwargs["screen_id"] == "1"
    assert kwargs["mic"] == "MacBook Pro Microphone"
    assert kwargs["marker_source"] == "global-capture"
    assert kwargs["until_enter"] is True
    assert "auto-detected" in result.output


def test_demo_respects_explicit_screen_and_mic(tmp_path):
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("sys.platform", "darwin"), \
         patch("capt.preflight.preflight", return_value=True), \
         patch("capt.targets.list_targets", return_value=FAKE_TARGETS), \
         patch("capt.record.beat.run_beat", return_value=_fake_result(tmp_path)) as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, [
            "demo", "my-demo", "--out", str(tmp_path),
            "--screen", "9", "--mic", "External Mic",
        ])

    assert result.exit_code == 0, result.output
    kwargs = run_beat_mock.call_args.kwargs
    assert kwargs["screen_id"] == "9"
    assert kwargs["mic"] == "External Mic"


def test_demo_no_mic_flag_skips_audio(tmp_path):
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("sys.platform", "darwin"), \
         patch("capt.preflight.preflight", return_value=True), \
         patch("capt.targets.list_targets", return_value=FAKE_TARGETS), \
         patch("capt.record.beat.run_beat", return_value=_fake_result(tmp_path)) as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "my-demo", "--out", str(tmp_path), "--no-mic"])

    assert result.exit_code == 0, result.output
    assert run_beat_mock.call_args.kwargs["mic"] is None


def test_demo_exits_nonzero_when_preflight_fails(tmp_path):
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("sys.platform", "darwin"), \
         patch("capt.preflight.preflight", return_value=False), \
         patch("capt.record.beat.run_beat") as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "my-demo", "--out", str(tmp_path)])

    assert result.exit_code != 0
    run_beat_mock.assert_not_called()


def test_demo_rejects_screen_and_window_together(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, [
        "demo", "my-demo", "--out", str(tmp_path), "--screen", "1", "--window", "2",
    ])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_demo_rejects_non_macos():
    with patch("capt.cli._is_wsl", return_value=False), patch("sys.platform", "linux"):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "my-demo"])
    assert result.exit_code != 0
    assert "macOS" in result.output


def test_demo_fails_clearly_when_screen_autodetect_fails(tmp_path):
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("sys.platform", "darwin"), \
         patch("capt.preflight.preflight", return_value=True), \
         patch("capt.targets.list_targets", return_value=None):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "my-demo", "--out", str(tmp_path)])

    assert result.exit_code != 0
    assert "auto-detect a screen" in result.output
