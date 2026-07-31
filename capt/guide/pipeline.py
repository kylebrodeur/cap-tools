"""Reusable guide-generation pipeline: ingest -> (transcribe) -> (structure)
-> render. Extracted from capt/cli.py's `guide` command so both the CLI and
a future chained command (Phase 3's `capt walkthrough`) can call one function
instead of duplicating this sequencing.

The deterministic path (ai=False) needs nothing beyond this package. The
`ai=True` path hands off to `cap_guide_analysis`, a private companion
package not distributed with cap-tools — see _import_structure() below.
"""

import json
from pathlib import Path
from typing import Optional


def _import_structure():
    """Import `structure` from the private cap_guide_analysis package.

    Kept as its own function (rather than an inline import in run_guide) so
    the "not installed" error is a single, clear message instead of a raw
    ModuleNotFoundError, and so tests can patch this one seam.
    """
    try:
        from cap_guide_analysis import structure
    except ImportError as e:
        raise RuntimeError(
            "capt guide --ai requires the private cap_guide_analysis package, "
            "which is not part of the public cap-tools distribution. Install it "
            "separately (uv pip install -e /path/to/cap-guide-analysis) or omit "
            "--ai for the deterministic pipeline (ingest + render, no LLM)."
        ) from e
    return structure


def run_guide(
    cap_path: str,
    out_dir: str,
    ai: bool = False,
    transcript_path: Optional[str] = None,
    model: Optional[str] = None,
    fmt: str = "both",
) -> dict:
    """Run the guide pipeline against a .cap project.

    Deterministic by default (ingest + render only). With ai=True, also
    transcribes (if no transcript_path given and audio-input.ogg exists) and
    runs the structure pass before rendering.

    Returns {"path": out_dir, "steps": int, "html": str | None, "md": str | None}.
    """
    from capt.guide.ingest import ingest
    from capt.guide.render import render

    cap_dir = Path(cap_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    result = ingest(str(cap_dir), out_dir, transcript_path=transcript_path, fmt=fmt)

    if ai:
        structure = _import_structure()
        from capt.guide.transcribe import transcribe

        resolved_transcript = transcript_path
        if not resolved_transcript:
            audio = cap_dir / "audio-input.ogg"
            if audio.exists():
                transcript_data = transcribe(str(audio))
                t_out = Path(out_dir) / "transcript.json"
                t_out.write_text(json.dumps(transcript_data, indent=2, ensure_ascii=False))
                resolved_transcript = str(t_out)

        if resolved_transcript:
            items_out = Path(out_dir) / "items.json"
            structure(resolved_transcript, str(items_out), model=model,
                     title=result["title"], recording=result["title"])

    display = cap_dir / "display.mp4"
    if not display.exists():
        meta = json.loads((cap_dir / "recording-meta.json").read_text())
        segs = meta.get("segments", [])
        if segs and "display" in segs[0]:
            display = cap_dir / segs[0]["display"]["path"]
        elif "display" in meta:
            display = cap_dir / meta["display"]["path"]

    items_path = Path(out_dir) / "items.json"
    if items_path.exists():
        render_result = render(str(items_path), str(display), out_dir, fmt=fmt)
    else:
        render_result = {"html": result.get("guide_html"), "md": result.get("guide_md")}

    return {
        "path": out_dir,
        "steps": result["step_count"],
        "html": render_result.get("html"),
        "md": render_result.get("md"),
    }
