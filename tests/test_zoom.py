"""Tests for capt.zoom — the auto-zoom-from-markers reference implementation
behind the "Record a multi-step walkthrough with automatic zoom" agent
workflow proposed upstream."""

from capt.zoom import build_zoom_segments, merge_zoom_segments


def test_build_zoom_segments_empty():
    assert build_zoom_segments([]) == []


def test_build_zoom_segments_single_event():
    segs = build_zoom_segments([{"label": "click", "elapsed_s": 10.0}])
    assert len(segs) == 1
    seg = segs[0]
    assert seg["start"] == 9.5  # pre_seconds default 0.5
    assert seg["end"] == 12.5  # hold_seconds default 2.5
    assert seg["amount"] == 2.0
    assert seg["mode"] == "auto"


def test_build_zoom_segments_clamps_start_at_zero():
    segs = build_zoom_segments([{"label": "start", "elapsed_s": 0.1}])
    assert segs[0]["start"] == 0  # max(0, 0.1 - 0.5) must not go negative


def test_build_zoom_segments_merges_close_events():
    events = [
        {"label": "a", "elapsed_s": 10.0},
        {"label": "b", "elapsed_s": 11.0},  # gap after "a"'s window (12.5) is negative -> merges
    ]
    segs = build_zoom_segments(events)
    assert len(segs) == 1
    assert segs[0]["start"] == 9.5
    assert segs[0]["end"] == 13.5  # extended to cover "b"'s window


def test_build_zoom_segments_keeps_far_events_separate():
    events = [
        {"label": "a", "elapsed_s": 10.0},
        {"label": "b", "elapsed_s": 30.0},  # far beyond min_gap_seconds
    ]
    segs = build_zoom_segments(events)
    assert len(segs) == 2


def test_build_zoom_segments_sorts_out_of_order_events():
    events = [
        {"label": "b", "elapsed_s": 30.0},
        {"label": "a", "elapsed_s": 10.0},
    ]
    segs = build_zoom_segments(events)
    assert [s["start"] for s in segs] == sorted(s["start"] for s in segs)


def test_build_zoom_segments_custom_amount():
    segs = build_zoom_segments([{"label": "x", "elapsed_s": 5.0}], amount=1.5)
    assert segs[0]["amount"] == 1.5


def test_merge_zoom_segments_replaces_only_zoom_segments():
    existing = {
        "aspectRatio": None,
        "timeline": {
            "segments": [{"recordingSegment": 0, "start": 0.0, "end": 9999}],
            "zoomSegments": [{"start": 1.0, "end": 2.0, "amount": 1.0, "mode": "auto"}],
        },
        "background": {"source": {"type": "wallpaper", "path": "sf.jpg"}},
        "camera": {"hide": True},
    }
    new_segments = [{"start": 5.0, "end": 8.0, "amount": 2.0, "mode": "auto"}]

    merged = merge_zoom_segments(existing, new_segments)

    assert merged["timeline"]["zoomSegments"] == new_segments
    # Everything else must survive untouched.
    assert merged["timeline"]["segments"] == existing["timeline"]["segments"]
    assert merged["background"] == existing["background"]
    assert merged["camera"] == existing["camera"]


def test_merge_zoom_segments_does_not_mutate_input():
    existing = {"timeline": {"zoomSegments": []}}
    new_segments = [{"start": 1.0, "end": 2.0, "amount": 2.0, "mode": "auto"}]

    merge_zoom_segments(existing, new_segments)

    assert existing["timeline"]["zoomSegments"] == []  # untouched


def test_merge_zoom_segments_handles_missing_timeline_key():
    existing = {"background": {"source": {"type": "color"}}}
    new_segments = [{"start": 1.0, "end": 2.0, "amount": 2.0, "mode": "auto"}]

    merged = merge_zoom_segments(existing, new_segments)

    assert merged["timeline"]["zoomSegments"] == new_segments
    assert merged["background"] == existing["background"]
