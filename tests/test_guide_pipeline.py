import json
from unittest.mock import MagicMock, patch

from capt.guide.pipeline import run_guide


def test_run_guide_deterministic_path_ingests_and_renders(tmp_path):
    cap_dir = tmp_path / "full.cap"
    cap_dir.mkdir()
    (cap_dir / "display.mp4").write_bytes(b"")
    out_dir = tmp_path / "out"

    fake_ingest = MagicMock(return_value={"title": "T", "step_count": 3})
    fake_render = MagicMock(return_value={"html": "out/guide.html", "md": None})

    with patch("capt.guide.ingest.ingest", fake_ingest), \
         patch("capt.guide.render.render", fake_render):
        result = run_guide(str(cap_dir), str(out_dir))

    fake_ingest.assert_called_once_with(str(cap_dir), str(out_dir), transcript_path=None)
    # No items.json exists on this path (ingest is mocked and writes nothing,
    # and structure() never runs without --ai), so run_guide correctly takes
    # the fallback branch and never calls render() — the html path below is
    # the ingest-produced guide.html, not fake_render's mocked return value.
    assert result == {"path": str(out_dir), "steps": 3, "html": str(out_dir / "guide.html"), "md": None}


def test_run_guide_ai_path_transcribes_and_structures_without_out_path_kwarg(tmp_path):
    # Regression test for the TypeError bug: transcribe() takes no out_path
    # kwarg. run_guide must call it with just audio_path and write the
    # result itself.
    cap_dir = tmp_path / "full.cap"
    cap_dir.mkdir()
    (cap_dir / "display.mp4").write_bytes(b"")
    (cap_dir / "audio-input.ogg").write_bytes(b"")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    fake_ingest = MagicMock(return_value={"title": "T", "step_count": 1})
    fake_transcribe = MagicMock(return_value={"duration": 1.0, "text": "hi", "segments": []})
    fake_structure = MagicMock(return_value={})
    fake_render = MagicMock(return_value={"html": "out/guide.html", "md": "out/guide.md"})

    with patch("capt.guide.ingest.ingest", fake_ingest), \
         patch("capt.guide.transcribe.transcribe", fake_transcribe), \
         patch("capt.guide.structure.structure", fake_structure), \
         patch("capt.guide.render.render", fake_render):
        run_guide(str(cap_dir), str(out_dir), ai=True)

    fake_transcribe.assert_called_once_with(str(cap_dir / "audio-input.ogg"))
    written = json.loads((out_dir / "transcript.json").read_text())
    assert written["text"] == "hi"
    fake_structure.assert_called_once()


def test_run_guide_ai_path_uses_given_transcript_path_without_transcribing(tmp_path):
    cap_dir = tmp_path / "full.cap"
    cap_dir.mkdir()
    (cap_dir / "display.mp4").write_bytes(b"")
    out_dir = tmp_path / "out"
    transcript = tmp_path / "given.json"
    transcript.write_text(json.dumps({"segments": []}))

    fake_ingest = MagicMock(return_value={"title": "T", "step_count": 1})
    fake_transcribe = MagicMock()
    fake_structure = MagicMock(return_value={})
    fake_render = MagicMock(return_value={"html": "out/guide.html", "md": None})

    with patch("capt.guide.ingest.ingest", fake_ingest), \
         patch("capt.guide.transcribe.transcribe", fake_transcribe), \
         patch("capt.guide.structure.structure", fake_structure), \
         patch("capt.guide.render.render", fake_render):
        run_guide(str(cap_dir), str(out_dir), ai=True, transcript_path=str(transcript))

    fake_transcribe.assert_not_called()
    fake_structure.assert_called_once()
