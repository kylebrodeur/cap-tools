from unittest.mock import MagicMock, patch

import pytest

from capt.record.beat import BeatResult, run_beat


def _patch_all(**overrides):
    """Patch every external call run_beat makes; override specific ones per test."""
    defaults = dict(
        _start_recording=MagicMock(return_value={"recordingId": "rec-1", "path": "/tmp/full.cap"}),
        _stop_recording=MagicMock(return_value={"recordingMetaExists": True}),
        _validate_project=MagicMock(return_value={"valid": True}),
        drive_steps=MagicMock(),
        read_config=MagicMock(return_value={"timeline": {"zoomSegments": []}}),
        write_config=MagicMock(),
        cap_export=MagicMock(return_value={"path": "/tmp/out.mp4"}),
    )
    defaults.update(overrides)
    patches = [
        patch("capt.record.beat._start_recording", defaults["_start_recording"]),
        patch("capt.record.beat._stop_recording", defaults["_stop_recording"]),
        patch("capt.record.beat._validate_project", defaults["_validate_project"]),
        patch("capt.record.steps.drive_steps", defaults["drive_steps"]),
        patch("capt.record.beat.read_config", defaults["read_config"]),
        patch("capt.record.beat.write_config", defaults["write_config"]),
        patch("capt.record.beat.cap_export", defaults["cap_export"]),
    ]
    return patches, defaults


def test_run_beat_happy_path_returns_beat_result(tmp_path):
    patches, mocks = _patch_all()
    for p in patches:
        p.start()
    try:
        result = run_beat(
            url="https://example.com",
            steps=[{"action": "click", "selector": "#go"}],
            out_dir=str(tmp_path),
            name="full",
        )
    finally:
        for p in patches:
            p.stop()

    assert isinstance(result, BeatResult)
    assert result.recording_id == "rec-1"
    assert result.cap_path == str(tmp_path / "full.cap")
    assert result.export_path is None
    mocks["drive_steps"].assert_called_once()
    mocks["_stop_recording"].assert_called_once_with("rec-1")
    mocks["write_config"].assert_called_once()


def test_run_beat_stops_recording_even_if_driving_raises(tmp_path):
    patches, mocks = _patch_all(drive_steps=MagicMock(side_effect=RuntimeError("boom")))
    for p in patches:
        p.start()
    try:
        with pytest.raises(RuntimeError, match="boom"):
            run_beat(url="https://example.com", steps=[], out_dir=str(tmp_path))
    finally:
        for p in patches:
            p.stop()

    mocks["_stop_recording"].assert_called_once_with("rec-1")


def test_run_beat_continues_to_export_if_zoom_merge_fails(tmp_path, capsys):
    patches, mocks = _patch_all(read_config=MagicMock(side_effect=RuntimeError("cap not reachable")))
    for p in patches:
        p.start()
    try:
        result = run_beat(
            url="https://example.com", steps=[], out_dir=str(tmp_path),
            export_to=str(tmp_path / "out.mp4"),
        )
    finally:
        for p in patches:
            p.stop()

    mocks["write_config"].assert_not_called()
    mocks["cap_export"].assert_called_once()
    assert result.export_path == "/tmp/out.mp4"
    assert "continuing without it" in capsys.readouterr().out


def test_run_beat_does_not_export_when_export_to_is_none(tmp_path):
    patches, mocks = _patch_all()
    for p in patches:
        p.start()
    try:
        result = run_beat(url="https://example.com", steps=[], out_dir=str(tmp_path))
    finally:
        for p in patches:
            p.stop()

    mocks["cap_export"].assert_not_called()
    assert result.export_path is None


def test_run_beat_global_capture_starts_and_stops_capture(tmp_path):
    patches, mocks = _patch_all()
    fake_capture = MagicMock()
    with patch("capt.record.macos_capture.GlobalCapture", return_value=fake_capture) as gc_cls:
        for p in patches:
            p.start()
        try:
            run_beat(
                url=None, steps=[], out_dir=str(tmp_path),
                marker_source="global-capture",
            )
        finally:
            for p in patches:
                p.stop()

    gc_cls.assert_called_once()
    fake_capture.start.assert_called_once()
    fake_capture.stop.assert_called_once()


def test_run_beat_skips_driving_when_no_url_and_steps_marker_source(tmp_path):
    patches, mocks = _patch_all()
    for p in patches:
        p.start()
    try:
        run_beat(url=None, steps=[], out_dir=str(tmp_path), marker_source="steps")
    finally:
        for p in patches:
            p.stop()

    mocks["drive_steps"].assert_not_called()
