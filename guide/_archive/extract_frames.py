#!/usr/bin/env python3
"""
extract_frames.py — Pull a frame at click+OFFSET seconds for each click event.

Usage:
    uv run spike/extract_frames.py

Reads:
    spike-output/recording/recording.mp4
    spike-output/recording/events.json
Writes:
    spike-output/frames/step_NN_tT.T.jpg
"""

import json
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SPIKE_ROOT = Path(__file__).parent / "spike-output"
RECORDING  = SPIKE_ROOT / "recording" / "recording.mp4"
EVENTS     = SPIKE_ROOT / "recording" / "events.json"
FRAMES_DIR = SPIKE_ROOT / "frames"
OFFSET     = 0.5    # seconds after click to capture frame
JPEG_Q     = 2      # ffmpeg -q:v — 1=best, 31=worst; 2 = very high quality
# ─────────────────────────────────────────────────────────────────────────────


def check_inputs():
    missing = []
    if not RECORDING.exists():
        missing.append(str(RECORDING))
    if not EVENTS.exists():
        missing.append(str(EVENTS))
    if missing:
        print("Missing required files:")
        for m in missing:
            print(f"  {m}")
        print("\nRun record.py first.")
        sys.exit(1)


def extract(index: int, click_t: float, recording: Path, out_dir: Path) -> Path:
    t = round(click_t + OFFSET, 3)
    out = out_dir / f"step_{index:02d}_t{t:.1f}.jpg"
    result = subprocess.run(
        [
            "ffmpeg",
            "-ss", str(t),
            "-i", str(recording),
            "-vframes", "1",
            "-q:v", str(JPEG_Q),
            "-y", str(out),
        ],
        capture_output=True,
    )
    return out if out.exists() else None


def main():
    check_inputs()
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    events = json.loads(EVENTS.read_text())
    if not events:
        print("events.json is empty — nothing to extract.")
        sys.exit(1)

    print(f"Extracting {len(events)} frames (+{OFFSET}s offset per click)...\n")

    ok = 0
    for i, ev in enumerate(events, 1):
        out = extract(i, ev["t"], RECORDING, FRAMES_DIR)
        if out:
            print(f"  [{i:02d}] click @ {ev['t']:.1f}s → frame @ {ev['t'] + OFFSET:.1f}s  {out.name}")
            ok += 1
        else:
            print(f"  [{i:02d}] click @ {ev['t']:.1f}s → FAILED (timestamp past end of video?)")

    print(f"\n  {ok}/{len(events)} frames extracted → {FRAMES_DIR}")
    print()
    print("Next: run  uv run spike/transcribe.py")
    print("      then uv run spike/assemble.py")


if __name__ == "__main__":
    main()
