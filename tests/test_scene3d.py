"""Tests for capt.scene3d — the 3D camera-scene builder behind
`capt scene` (Cap 0.6+ timeline.camera3dSegments)."""

import pytest

from capt.scene3d import (
    STYLES,
    build_scene_segments,
    merge_scene_segments,
)


def test_build_scene_segments_flat_is_noop():
    assert build_scene_segments([{"label": "click", "elapsed_s": 5.0}], style="flat") == []


def test_unknown_style_raises_listing_valid_styles():
    with pytest.raises(ValueError, match="reveal"):
        build_scene_segments([], style="dolly")


def test_zero_or_negative_duration_raises():
    with pytest.raises(ValueError):
        build_scene_segments([], style="reveal", duration=0)
    with pytest.raises(ValueError):
        build_scene_segments([], style="orbit", duration=-3)


def test_reveal_ignores_events_and_spans_full_clip():
    segs = build_scene_segments([{"label": "click", "elapsed_s": 3.0}],
                                style="reveal", duration=30)
    assert len(segs) == 1
    assert segs[0]["start"] == 0.0
    assert segs[0]["end"] == 30
    assert segs[0]["enabled"] is True
    props = segs[0]["properties"]
    assert props["tiltX"] == 8.0 and props["tiltY"] == -12.0
    assert props["zoom"] == 1.08 and props["fov"] == 50.0


def test_punch_window_math_matches_zoom():
    # same window math as build_zoom_segments: 0.8s pre, 2.5s hold
    segs = build_scene_segments([{"label": "click", "elapsed_s": 10.0}], style="punch")
    assert len(segs) == 1
    assert segs[0]["start"] == 9.2  # max(0, 10.0 - 0.8)
    assert segs[0]["end"] == 12.5   # 10.0 + 2.5
    assert segs[0]["properties"]["tiltX"] == 10.0
    assert segs[0]["properties"]["tiltY"] == -15.0
    assert segs[0]["properties"]["zoom"] == 1.12


def test_punch_merges_close_event_windows():
    # gap after "a"'s window (1.0+2.5=3.5) to "b"'s start (4.0-0.8=3.2) is
    # negative -> one merged segment
    segs = build_scene_segments([
        {"label": "a", "elapsed_s": 1.0},
        {"label": "b", "elapsed_s": 4.0},
    ], style="punch")
    assert len(segs) == 1
    assert segs[0]["end"] == 6.5  # b's window end


def test_punch_keeps_far_events_separate():
    segs = build_scene_segments([
        {"label": "a", "elapsed_s": 0.0},
        {"label": "b", "elapsed_s": 30.0},  # beyond a's window + 1s gap
    ], style="punch")
    assert len(segs) == 2


def test_punch_clamps_start_at_zero():
    segs = build_scene_segments([{"label": "start", "elapsed_s": 0.1}], style="punch")
    assert segs[0]["start"] == 0


def test_orbit_is_one_segment_with_two_keyframe_tiltY_track():
    segs = build_scene_segments([], style="orbit", duration=12)
    assert len(segs) == 1
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 12
    track = segs[0]["tracks"]["tiltY"]
    assert len(track) == 2
    assert track[0]["time"] == 0.0 and track[0]["value"] == -20.0
    assert track[1]["time"] == 12 and track[1]["value"] == 20.0
    # properties carry the static pose; animated axis is in tracks
    assert segs[0]["properties"]["tiltX"] == 6.0


def test_orbit_without_events_or_duration_raises():
    with pytest.raises(ValueError, match="duration"):
        build_scene_segments([], style="orbit")


def test_duration_defaults_from_last_event():
    segs = build_scene_segments([{"label": "click", "elapsed_s": 8.0}], style="reveal")
    assert segs[0]["end"] == 10.5  # 8.0 + 2.5 hold


def test_styles_constant_matches_cli_choices():
    assert set(STYLES) == {"reveal", "punch", "orbit", "flat"}


def test_merge_scene_segments_replaces_not_appends():
    existing = {
        "background": {"source": {"type": "color", "value": [0, 0, 0], "alpha": 255}},
        "camera": {"hide": True},
        "timeline": {
            "segments": [{"recordingSegment": 0, "timescale": 1.0, "start": 0.0, "end": 9999}],
            "zoomSegments": [{"start": 1.0, "end": 2.0, "amount": 2.0, "mode": "auto"}],
            "camera3dSegments": [{"start": 0.0, "end": 5.0, "enabled": True}],
            "maskSegments": [],
        },
    }
    new_segments = [{"start": 0.0, "end": 12.0, "enabled": True}]
    merged = merge_scene_segments(existing, new_segments)
    assert merged["timeline"]["camera3dSegments"] == new_segments  # replaced
    assert merged["timeline"]["zoomSegments"] == existing["timeline"]["zoomSegments"]  # zoom survives
    assert merged["background"] == existing["background"]  # everything else untouched


def test_merge_scene_segments_handles_missing_timeline_key():
    existing = {"background": {"source": {"type": "color"}}}
    merged = merge_scene_segments(existing, [{"start": 0.0, "end": 4.0}])
    assert merged["timeline"]["camera3dSegments"] == [{"start": 0.0, "end": 4.0}]


def test_merge_scene_segments_does_not_mutate_input():
    existing = {"timeline": {"camera3dSegments": [{"start": 0.0, "end": 1.0}]}}
    original = [{"start": 0.0, "end": 1.0}]
    merged = merge_scene_segments(existing, [{"start": 0.0, "end": 9.0}])
    assert existing["timeline"]["camera3dSegments"] == original
    assert merged is not existing