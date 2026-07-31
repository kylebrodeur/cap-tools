from unittest.mock import MagicMock, patch

import pytest

from capt.record.beat import BeatResult, _run_cap_json, _start_recording, run_beat


def test_run_cap_json_parses_pretty_printed_multiline_output():
    # Regression test: `cap project validate` returns pretty-printed,
    # multi-line JSON (unlike record start/stop's compact single line).
    # The old implementation only tried json.loads(out.splitlines()[-1]),
    # which is just "}" for pretty output — always a JSONDecodeError.
    pretty = (
        '{\n'
        '  "projectPath": "/tmp/full.cap",\n'
        '  "valid": true,\n'
        '  "checks": [\n'
        '    {"role": "recordingMeta", "exists": true}\n'
        '  ]\n'
        '}'
    )
    fake_proc = MagicMock(returncode=0, stdout=pretty, stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        result = _run_cap_json("project", "validate", "/tmp/full.cap")

    assert result["valid"] is True
    assert result["projectPath"] == "/tmp/full.cap"


def test_start_recording_uses_window_over_screen_when_both_given():
    fake_run_cap_json = MagicMock(return_value={"recordingId": "rec-1"})
    with patch("capt.record.beat._run_cap_json", fake_run_cap_json):
        _start_recording("/tmp/full.cap", screen_id="1", window_id="683")

    args = fake_run_cap_json.call_args[0]
    assert "--window" in args and "683" in args
    assert "--screen" not in args


def test_start_recording_falls_back_to_screen_when_no_window():
    fake_run_cap_json = MagicMock(return_value={"recordingId": "rec-1"})
    with patch("capt.record.beat._run_cap_json", fake_run_cap_json):
        _start_recording("/tmp/full.cap", screen_id="1")

    args = fake_run_cap_json.call_args[0]
    assert "--screen" in args and "1" in args
    assert "--window" not in args


def test_run_beat_passes_window_id_to_start_recording(tmp_path):
    patches, mocks = _patch_all()
    for p in patches:
        p.start()
    try:
        run_beat(url="https://example.com", steps=[], out_dir=str(tmp_path), window_id="683")
    finally:
        for p in patches:
            p.stop()

    mocks["_start_recording"].assert_called_once()
    _, kwargs = mocks["_start_recording"].call_args
    assert kwargs.get("window_id") == "683"


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


def test_run_beat_stops_recording_even_if_capture_start_raises(tmp_path):
    # Regression test: capture/tracker setup must live inside the try/finally
    # so a failure in GlobalCapture.start() (e.g. missing Input Monitoring
    # permission) still stops the already-running Cap session instead of
    # orphaning it.
    patches, mocks = _patch_all()
    fake_capture = MagicMock()
    fake_capture.start.side_effect = PermissionError("Input Monitoring not granted")
    with patch("capt.record.macos_capture.GlobalCapture", return_value=fake_capture):
        for p in patches:
            p.start()
        try:
            with pytest.raises(PermissionError):
                run_beat(
                    url=None, steps=[], out_dir=str(tmp_path),
                    marker_source="global-capture",
                )
        finally:
            for p in patches:
                p.stop()

    mocks["_stop_recording"].assert_called_once_with("rec-1")
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


def test_run_beat_continues_to_export_when_config_step_raises_system_exit(tmp_path, capsys):
    # capt.config.read_config/write_config actually call sys.exit(...) on a real
    # `cap project config get/set` subprocess failure, not a plain Exception —
    # SystemExit subclasses BaseException, so the zoom/config except clause must
    # catch it too or a real config failure aborts the whole beat.
    patches, mocks = _patch_all(
        read_config=MagicMock(side_effect=SystemExit("cap project config get failed: boom")),
    )
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
    assert isinstance(result, BeatResult)
    assert result.export_path == "/tmp/out.mp4"
    assert "continuing without it" in capsys.readouterr().out


def test_run_beat_creates_tracker_after_start_recording(tmp_path):
    # The marker clock (create_tracker) must be anchored to when the
    # recording actually started, not to whenever run_beat() happened to be
    # called — _start_recording() blocks on Cap's session-readiness poll,
    # which can take real time. If create_tracker() ran first, every
    # elapsed_s marker would be measured from before recording began,
    # systematically shifting zoom segments early.
    call_order = []

    def fake_start_recording(cap_path, screen_id, window_id=None):
        call_order.append("start_recording")
        return {"recordingId": "rec-1"}

    def fake_create_tracker():
        call_order.append("create_tracker")
        return MagicMock()

    patches, mocks = _patch_all(
        _start_recording=MagicMock(side_effect=fake_start_recording),
    )
    with patch("capt.record.beat.create_tracker", side_effect=fake_create_tracker):
        for p in patches:
            p.start()
        try:
            run_beat(url="https://example.com", steps=[], out_dir=str(tmp_path))
        finally:
            for p in patches:
                p.stop()

    assert call_order == ["start_recording", "create_tracker"]


def test_run_beat_starts_global_capture_after_start_recording(tmp_path):
    # Same ordering requirement as create_tracker above, but for the
    # global-capture path: GlobalCapture must be constructed/started only
    # after the recording call returns.
    call_order = []

    def fake_start_recording(cap_path, screen_id, window_id=None):
        call_order.append("start_recording")
        return {"recordingId": "rec-1"}

    fake_capture = MagicMock()

    def fake_global_capture(tracker):
        call_order.append("global_capture_created")
        return fake_capture

    patches, mocks = _patch_all(
        _start_recording=MagicMock(side_effect=fake_start_recording),
    )
    with patch("capt.record.macos_capture.GlobalCapture", side_effect=fake_global_capture):
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

    assert call_order == ["start_recording", "global_capture_created"]
    fake_capture.start.assert_called_once()
    fake_capture.stop.assert_called_once()


def test_run_beat_steps_plus_global_capture_drives_steps_and_captures(tmp_path):
    # marker_source="steps+global-capture" is the mode the project's
    # playbook recommends for real use — it must drive steps AND run
    # global-capture at the same time.
    patches, mocks = _patch_all()
    fake_capture = MagicMock()
    with patch("capt.record.macos_capture.GlobalCapture", return_value=fake_capture) as gc_cls:
        for p in patches:
            p.start()
        try:
            run_beat(
                url="https://example.com",
                steps=[{"action": "click", "selector": "#go"}],
                out_dir=str(tmp_path),
                marker_source="steps+global-capture",
            )
        finally:
            for p in patches:
                p.stop()

    mocks["drive_steps"].assert_called_once()
    gc_cls.assert_called_once()
    fake_capture.start.assert_called_once()
    fake_capture.stop.assert_called_once()


def test_run_beat_stops_recording_even_if_capture_stop_raises(tmp_path):
    patches, mocks = _patch_all()
    fake_capture = MagicMock()
    fake_capture.stop.side_effect = RuntimeError("capture stop boom")
    with patch("capt.record.macos_capture.GlobalCapture", return_value=fake_capture):
        for p in patches:
            p.start()
        try:
            with pytest.raises(RuntimeError, match="capture stop boom"):
                run_beat(
                    url=None, steps=[], out_dir=str(tmp_path),
                    marker_source="global-capture",
                )
        finally:
            for p in patches:
                p.stop()

    mocks["_stop_recording"].assert_called_once_with("rec-1")
