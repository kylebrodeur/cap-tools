"""Tests for capt.sections — section extraction from styled recordings."""

import json
import pytest

from capt.sections import (
    load_sections,
    sections_from_beats,
    sections_from_events,
)


def test_sections_from_beats_span_beat_to_next_beat():
    beats = [
        {"index": 0, "label": "open", "elapsed_s": 1.5, "ok": True},
        {"index": 1, "label": "script", "elapsed_s": 24.0, "ok": True},
        {"index": 2, "label": "stage", "elapsed_s": 46.2, "ok": True},
    ]
    s = sections_from_beats(beats)
    assert [(x["name"], x["start_s"], x["end_s"]) for x in s] == [
        ("open", 1.5, 24.0), ("script", 24.0, 46.2), ("stage", 46.2, 47.2),
    ]  # last beat holds default_hold_s (1.0) past its start


def test_sections_clamp_negative_start():
    beats = [{"index": 0, "label": "early", "elapsed_s": -2.0, "ok": True}]
    s = sections_from_beats(beats)
    assert s[0]["start_s"] == 0.0
    assert s[0]["end_s"] > 0


def test_sections_from_events_uses_hold_default():
    evs = [{"label": "click:a", "elapsed_s": 3.0}, {"label": "click:b", "elapsed_s": 9.0}]
    s = sections_from_events(evs)
    assert s[0] == {"name": "click:a", "start_s": 3.0, "end_s": 9.0}
    assert s[1]["end_s"] == 11.5  # 9.0 + 2.5 event hold default


def test_load_sections_accepts_beats_report(tmp_path):
    p = tmp_path / "take.beats.json"
    p.write_text(json.dumps({"complete": True, "beats": [
        {"index": 0, "label": "a", "elapsed_s": 1.0, "ok": True}]}))
    s = load_sections(str(p))
    assert len(s) == 1 and s[0]["name"] == "a"


def test_load_sections_accepts_explicit_sections(tmp_path):
    p = tmp_path / "sections.json"
    p.write_text(json.dumps([{"name": "intro", "start_s": 0.0, "end_s": 5.0}]))
    assert load_sections(str(p)) == [{"name": "intro", "start_s": 0.0, "end_s": 5.0}]


def test_load_sections_accepts_events_sidecar(tmp_path):
    p = tmp_path / "take.events.json"
    p.write_text(json.dumps([{"label": "m", "elapsed_s": 2.0}]))
    s = load_sections(str(p))
    assert s[0]["name"] == "m" and s[0]["start_s"] == 2.0


def test_load_sections_rejects_unrecognized(tmp_path):
    p = tmp_path / "junk.json"
    p.write_text(json.dumps({"unrelated": True}))
    with pytest.raises(ValueError, match="beats report"):
        load_sections(str(p))


def test_cut_section_reencodes_exact_duration(tmp_path):
    """Cut a known window out of a synthetic 10s video; duration must match."""
    import subprocess
    video = tmp_path / "take.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", "testsrc=duration=10:size=320x180:rate=30",
        "-c:v", "libx264", str(video)], check=True)
    from capt.sections import cut_section
    out = cut_section(str(video), {"name": "mid", "start_s": 2.0, "end_s": 5.0},
                      str(tmp_path / "mid.mp4"))
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", out], capture_output=True, text=True)
    assert abs(float(probe.stdout.strip()) - 3.0) < 0.15


def test_cut_section_stream_copy_produces_output(tmp_path):
    import subprocess
    video = tmp_path / "take.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", "testsrc=duration=10:size=320x180:rate=30",
        "-c:v", "libx264", str(video)], check=True)
    from capt.sections import cut_section
    out = cut_section(str(video), {"name": "x", "start_s": 1.0, "end_s": 4.0},
                      str(tmp_path / "x.mp4"), reencode=False)
    assert __import__("pathlib").Path(out).exists()


def test_export_sections_names_outputs_after_take(tmp_path):
    import subprocess
    video = tmp_path / "styled.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
        "-i", "testsrc=duration=6:size=320x180:rate=30",
        "-c:v", "libx264", str(video)], check=True)
    from capt.sections import export_sections
    sections = [{"name": "a bit!", "start_s": 0.0, "end_s": 2.0}]
    outs = export_sections(str(tmp_path / "demo.cap"), str(video),
                           str(tmp_path / "out"), sections)
    assert len(outs) == 1
    assert outs[0].endswith("demo.a-bit.mp4")  # named after project_cap stem