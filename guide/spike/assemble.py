#!/usr/bin/env python3
"""
assemble.py — Build an HTML guide from events.json + transcript.json + frames/.

Usage:
    uv run spike/assemble.py

Reads:
    spike-output/recording/events.json
    spike-output/transcript/transcript.json
    spike-output/frames/step_NN_*.jpg
Writes:
    spike-output/output/guide.html   (self-contained, base64-embedded images)
"""

import base64
import json
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SPIKE_ROOT = Path(__file__).parent / "spike-output"
EVENTS     = SPIKE_ROOT / "recording" / "events.json"
TRANSCRIPT = SPIKE_ROOT / "transcript" / "transcript.json"
FRAMES_DIR = SPIKE_ROOT / "frames"
OUTPUT     = SPIKE_ROOT / "output" / "guide.html"
# ─────────────────────────────────────────────────────────────────────────────


def load_segments(transcript_path: Path) -> list:
    """Load transcript segments, handling both flat and nested formats."""
    data = json.loads(transcript_path.read_text())

    # Your existing tool's format: {"whisper_result": {"segments": [...]}}
    if isinstance(data, dict) and "whisper_result" in data:
        return data["whisper_result"].get("segments", [])

    # Standard flat format: {"segments": [...]}
    if isinstance(data, dict) and "segments" in data:
        return data["segments"]

    # Raw list
    if isinstance(data, list):
        return data

    return []


def nearest_segment(segments: list, t: float) -> str:
    """Find transcript segment whose start is closest to timestamp t."""
    if not segments:
        return ""
    best = min(segments, key=lambda s: abs(s.get("start", 0) - t))
    return best.get("text", "").strip()


def b64_image(path: Path) -> str:
    return f"data:image/jpeg;base64,{base64.b64encode(path.read_bytes()).decode()}"


def build_html(steps: list) -> str:
    step_cards = ""
    for s in steps:
        step_cards += f"""
    <div class="step-card">
      <div class="step-label">Step {s['num']}</div>
      <p class="step-text">{s['text']}</p>
      <img class="screenshot" src="{s['img_b64']}" alt="Step {s['num']} screenshot">
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Spike Guide Output</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    font-family: Arial, Helvetica, sans-serif;
    font-size: 14px;
    line-height: 1.65;
    color: #222;
    max-width: 860px;
    margin: 40px auto;
    padding: 0 24px 80px;
    background: #fff;
  }}
  h1 {{ font-size: 22px; font-weight: 700; color: #1A3A5C; margin: 0 0 6px; }}
  .meta {{ font-size: 12px; color: #999; margin: 0 0 32px; }}
  .step-card {{
    border: 1px solid #D0DFF0;
    border-radius: 8px;
    padding: 18px 20px;
    margin: 0 0 20px;
    background: #fff;
  }}
  .step-label {{
    font-size: 11px;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin: 0 0 6px;
  }}
  .step-text {{
    font-size: 14px;
    color: #222;
    margin: 0 0 14px;
  }}
  .screenshot {{
    max-width: 100%;
    border: 1px solid #ddd;
    border-radius: 4px;
    display: block;
  }}
</style>
</head>
<body>
<h1>Spike Guide Output</h1>
<p class="meta">{len(steps)} steps &nbsp;·&nbsp; generated from events.json + transcript.json + frames/</p>
{step_cards}
</body>
</html>"""


def main():
    # Validate inputs
    missing = []
    if not EVENTS.exists():
        missing.append(str(EVENTS))
    if not TRANSCRIPT.exists():
        missing.append(str(TRANSCRIPT))
    if missing:
        print("Missing required files:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    events   = json.loads(EVENTS.read_text())
    segments = load_segments(TRANSCRIPT)

    if not events:
        print("events.json is empty.")
        sys.exit(1)
    if not segments:
        print("No transcript segments found — check transcript.json format.")
        sys.exit(1)

    print(f"  {len(events)} click events")
    print(f"  {len(segments)} transcript segments")

    steps = []
    missing_frames = 0
    for i, ev in enumerate(events, 1):
        frame_matches = sorted(FRAMES_DIR.glob(f"step_{i:02d}_*.jpg"))
        if not frame_matches:
            missing_frames += 1
            continue
        steps.append({
            "num":     i,
            "t":       ev["t"],
            "text":    nearest_segment(segments, ev["t"]) or f"Step {i}",
            "img_b64": b64_image(frame_matches[0]),
        })

    if not steps:
        print("No steps assembled — run extract_frames.py first.")
        sys.exit(1)

    if missing_frames:
        print(f"  Warning: {missing_frames} events had no matching frame (skipped)")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_html(steps), encoding="utf-8")

    size_kb = OUTPUT.stat().st_size // 1024
    print(f"\n  Guide written → {OUTPUT}")
    print(f"  {len(steps)} steps  ·  {size_kb}KB")
    print()
    print("Open spike-output/output/guide.html in a browser to review.")


if __name__ == "__main__":
    main()
