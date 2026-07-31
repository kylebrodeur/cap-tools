from pathlib import Path

import av
import pytest

from capt.guide.ingest import _extract_frame, _video_duration


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
