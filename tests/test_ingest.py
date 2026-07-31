import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import av
import pytest

from capt.guide.ingest import (
    _extract_frame, _extract_frame_via_cap, _video_dimensions, _video_duration, ingest,
)


def _make_test_video(path: Path, duration_s: float = 2.0, fps: int = 10) -> None:
    """Write a tiny synthetic MP4 via PyAV — no external tools needed."""
    container = av.open(str(path), mode="w")
    stream = container.add_stream("libx264", rate=fps)
    stream.width = 32
    stream.height = 32
    stream.pix_fmt = "yuv420p"

    for i in range(int(duration_s * fps)):
        frame = av.VideoFrame(width=32, height=32, format="yuv420p")
        for plane in frame.planes:
            plane.update(bytes([i % 256]) * plane.buffer_size)
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def test_video_duration_reads_real_file(tmp_path):
    video = tmp_path / "clip.mp4"
    _make_test_video(video, duration_s=2.0, fps=10)

    duration = _video_duration(video)
    assert duration == pytest.approx(2.0, abs=0.2)


def test_video_duration_returns_zero_for_unreadable_file(tmp_path):
    bogus = tmp_path / "not-a-video.mp4"
    bogus.write_bytes(b"not actually a video")

    assert _video_duration(bogus) == 0.0


def test_extract_frame_writes_a_real_jpeg(tmp_path):
    video = tmp_path / "clip.mp4"
    _make_test_video(video, duration_s=2.0, fps=10)
    out = tmp_path / "frames" / "step.jpg"

    assert _extract_frame(video, 1.0, out) is True
    assert out.exists()
    with open(out, "rb") as f:
        assert f.read(3) == b"\xff\xd8\xff"  # JPEG magic bytes


def test_extract_frame_returns_false_for_unreadable_file(tmp_path):
    bogus = tmp_path / "not-a-video.mp4"
    bogus.write_bytes(b"not actually a video")
    out = tmp_path / "frames" / "step.jpg"

    assert _extract_frame(bogus, 1.0, out) is False


def test_video_dimensions_reads_real_file(tmp_path):
    video = tmp_path / "clip.mp4"
    _make_test_video(video, duration_s=1.0, fps=10)

    assert _video_dimensions(video) == (32, 32)


def test_video_dimensions_none_for_unreadable_file(tmp_path):
    bogus = tmp_path / "not-a-video.mp4"
    bogus.write_bytes(b"not actually a video")

    assert _video_dimensions(bogus) is None


def test_extract_frame_via_cap_decodes_jpeg_from_json(tmp_path):
    out = tmp_path / "frames" / "step.jpg"
    fake_jpeg = b"\xff\xd8\xff\xe0fakejpegbytes"
    fake_proc = MagicMock(returncode=0, stdout=json.dumps({
        "jpeg_base64": base64.b64encode(fake_jpeg).decode(),
    }))
    with patch("subprocess.run", return_value=fake_proc) as run_mock:
        assert _extract_frame_via_cap(tmp_path, 1.5, out, fps=30, width=1920, height=1080) is True

    assert out.read_bytes() == fake_jpeg
    args = run_mock.call_args[0][0]
    assert "export-preview" in args
    assert "1.500" in args


def test_extract_frame_via_cap_returns_false_when_cap_missing(tmp_path):
    out = tmp_path / "frames" / "step.jpg"
    with patch("subprocess.run", side_effect=FileNotFoundError("no cap")):
        assert _extract_frame_via_cap(tmp_path, 1.0, out, fps=30, width=1920, height=1080) is False
    assert not out.exists()


def test_extract_frame_via_cap_returns_false_on_nonzero_exit(tmp_path):
    out = tmp_path / "frames" / "step.jpg"
    fake_proc = MagicMock(returncode=1, stdout="", stderr="not a valid project")
    with patch("subprocess.run", return_value=fake_proc):
        assert _extract_frame_via_cap(tmp_path, 1.0, out, fps=30, width=1920, height=1080) is False


def test_extract_frame_via_cap_returns_false_on_unparseable_output(tmp_path):
    out = tmp_path / "frames" / "step.jpg"
    fake_proc = MagicMock(returncode=0, stdout="not json")
    with patch("subprocess.run", return_value=fake_proc):
        assert _extract_frame_via_cap(tmp_path, 1.0, out, fps=30, width=1920, height=1080) is False


def _make_cap_project(cap_dir: Path) -> None:
    cap_dir.mkdir()
    _make_test_video(cap_dir / "display.mp4", duration_s=2.0, fps=10)
    (cap_dir / "recording-meta.json").write_text(json.dumps({
        "pretty_name": "Test Recording",
        "display": {"path": "display.mp4"},
        "cursor": "cursor.json",
    }))
    (cap_dir / "cursor.json").write_text(json.dumps({
        "clicks": [{"time_ms": 500, "down": True}, {"time_ms": 550, "down": False}],
        "moves": [{"time_ms": 500, "x": 0.5, "y": 0.5}],
    }))


@pytest.mark.parametrize("fmt,expect_html,expect_md", [
    ("both", True, True),
    ("html", True, False),
    ("md", False, True),
])
def test_ingest_honors_fmt(tmp_path, fmt, expect_html, expect_md):
    # Regression test: ingest() used to always write guide.html and never
    # wrote markdown at all, regardless of the caller's requested format —
    # capt guide --format md (or --format both, without --ai) silently
    # produced no markdown file.
    #
    # _extract_frame_via_cap is forced to fail here so this test exercises
    # the PyAV fallback deterministically — it's not a real Cap project, so
    # `cap export-preview` would fail anyway, but forcing it keeps the test
    # from depending on whether `cap` happens to be installed in whatever
    # environment runs the suite.
    cap_dir = tmp_path / "full.cap"
    _make_cap_project(cap_dir)
    out_dir = tmp_path / "out"

    with patch("capt.guide.ingest._extract_frame_via_cap", return_value=False):
        result = ingest(str(cap_dir), str(out_dir), fmt=fmt)

    assert (result["guide_html"] is not None) == expect_html
    assert (result["guide_md"] is not None) == expect_md
    if expect_html:
        assert Path(result["guide_html"]).exists()
    if expect_md:
        assert Path(result["guide_md"]).exists()
        assert "Test Recording" in Path(result["guide_md"]).read_text()


def test_ingest_prefers_cap_native_extraction_when_it_succeeds(tmp_path):
    cap_dir = tmp_path / "full.cap"
    _make_cap_project(cap_dir)
    out_dir = tmp_path / "out"

    def fake_extract_via_cap(cap_dir_arg, t_s, out, fps, width, height):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\xff\xd8\xff\xe0fake")
        return True

    with patch("capt.guide.ingest._extract_frame_via_cap", side_effect=fake_extract_via_cap), \
         patch("capt.guide.ingest._extract_frame") as fake_pyav_extract:
        result = ingest(str(cap_dir), str(out_dir))

    assert result["step_count"] == 1
    fake_pyav_extract.assert_not_called()
