#!/usr/bin/env python3
"""
cap_ingest.py — turn a Cap **Studio** .cap recording into an illustrated guide.

Pure post-processor over the Cap on-disk format (see
SPIKE_IMPROVEMENT_BRIEF.md §7.1). No capture code: it reads what Cap already
recorded and assembles a screenshot-per-click guide.

Usage:
    uv run spike/cap_ingest.py "<path-to-recording.cap>"
    uv run spike/cap_ingest.py "<...>.cap" --offset 0.5 --out spike-output/cap

What it does:
  1. Reads recording-meta.json (Studio single- or multi-segment).
  2. For each segment, loads cursor.json → meaningful clicks (down==true,
     debounced) and the move trail (for click position).
  3. Extracts a frame from that segment's display.mp4 at click_time + OFFSET.
  4. Joins each click to the nearest word-level caption IF captions.json exists
     (Cap's transcript); otherwise leaves the caption blank (no audio/transcript
     in this recording — feed the mic track to the WSL tool when present).
  5. Writes a self-contained guide.html with a CSS click-marker overlay
     (cursor x/y are normalized 0..1, so they map straight onto the frame).
"""

import argparse
import base64
import html
import json
import subprocess
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
OFFSET_S       = 0.5     # seconds after a click to grab the frame (UI settled)
DEBOUNCE_MS    = 400.0   # drop a click within this of the previous kept click
DEBOUNCE_DIST  = 0.01    # ...and within this normalized distance (same spot)
JPEG_Q         = 2       # ffmpeg -q:v (1=best..31=worst)
LEFT_BUTTON_ONLY = False # Cap's cursor_num→button mapping is uncertain; keep all
# ─────────────────────────────────────────────────────────────────────────────


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def ffprobe_duration(path: Path) -> float:
    r = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def load_meta(cap_dir: Path) -> dict:
    meta_path = cap_dir / "recording-meta.json"
    if not meta_path.exists():
        sys.exit(f"Not a Cap recording (no recording-meta.json): {cap_dir}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def collect_segments(meta: dict) -> list[dict]:
    """Return ordered segments as {display, cursor, start_time, fps}.

    Handles Studio single-segment (top-level `display`) and multi-segment
    (`segments[]` whose items carry `display`). Rejects Instant mode.
    """
    segs = meta.get("segments")
    if isinstance(segs, list) and segs and isinstance(segs[0], dict) and "display" in segs[0]:
        out = []
        for s in segs:
            out.append({
                "display": s["display"]["path"],
                "cursor": s.get("cursor"),
                "start_time": s["display"].get("start_time", 0.0),
                "fps": s["display"].get("fps", 30),
            })
        return out
    if "display" in meta:  # single-segment studio
        return [{
            "display": meta["display"]["path"],
            "cursor": meta.get("cursor"),
            "start_time": meta["display"].get("start_time", 0.0),
            "fps": meta["display"].get("fps", 30),
        }]
    sys.exit(
        "This looks like a Cap Instant recording (single muxed output.mp4) or an "
        "unsupported layout. Re-record in Studio mode for per-stream cursor data."
    )


def load_cursor(cap_dir: Path, rel: str | None) -> tuple[list[dict], list[dict]]:
    if not rel:
        return [], []
    p = cap_dir / rel
    if not p.exists():
        return [], []
    data = json.loads(p.read_text(encoding="utf-8"))
    clicks = sorted(data.get("clicks", []), key=lambda c: c.get("time_ms", 0))
    moves = sorted(data.get("moves", []), key=lambda m: m.get("time_ms", 0))
    return clicks, moves


def meaningful_clicks(clicks: list[dict]) -> list[dict]:
    """Down-presses only, debounced by time + position-at-time later."""
    downs = [c for c in clicks if c.get("down")]
    if LEFT_BUTTON_ONLY:
        downs = [c for c in downs if c.get("cursor_num") in (0, 1)]
    return downs


def pos_at(moves: list[dict], t_ms: float) -> tuple[float, float] | None:
    """Cursor (x,y) normalized at time t: last move <= t, else earliest move."""
    if not moves:
        return None
    prev = None
    for m in moves:
        if m["time_ms"] <= t_ms:
            prev = m
        else:
            break
    chosen = prev or moves[0]
    return chosen.get("x"), chosen.get("y")


def extract_frame(display: Path, t_s: float, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    r = run([
        "ffmpeg", "-ss", f"{max(t_s, 0):.3f}", "-i", str(display),
        "-vframes", "1", "-q:v", str(JPEG_Q), "-y", str(out),
    ])
    return out.exists()


def load_captions(cap_dir: Path) -> list[dict]:
    p = cap_dir / "captions.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("segments", []) if isinstance(data, dict) else []


def load_transcript_file(path: Path) -> list[dict]:
    """Load our transcript schema: {segments:[{start,end,text,words}]} or a bare list."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data.get("segments", [])
    return data if isinstance(data, list) else []


def caption_at(segments: list[dict], t_s: float) -> str:
    if not segments:
        return ""
    # prefer the segment that contains t; else nearest by start
    for s in segments:
        if s.get("start", 0) <= t_s <= s.get("end", 0):
            return s.get("text", "").strip()
    return min(segments, key=lambda s: abs(s.get("start", 0) - t_s)).get("text", "").strip()


def b64(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def build_steps(cap_dir: Path, segments: list[dict], frames_dir: Path,
                caption_segments: list[dict]) -> list[dict]:
    steps: list[dict] = []
    seg_offset = 0.0  # cumulative seconds before this segment (global timeline)
    n = 0
    for si, seg in enumerate(segments):
        display = cap_dir / seg["display"]
        dur = ffprobe_duration(display)
        clicks, moves = load_cursor(cap_dir, seg["cursor"])
        downs = meaningful_clicks(clicks)

        last_t = -1e9
        last_xy = (-1.0, -1.0)
        for c in downs:
            t_ms = c["time_ms"]
            xy = pos_at(moves, t_ms) or (0.5, 0.5)
            # debounce: too soon AND too close to the previous kept click
            if (t_ms - last_t) < DEBOUNCE_MS and abs(xy[0] - last_xy[0]) < DEBOUNCE_DIST \
               and abs(xy[1] - last_xy[1]) < DEBOUNCE_DIST:
                continue
            last_t, last_xy = t_ms, xy

            n += 1
            local_s = t_ms / 1000.0
            global_s = seg_offset + local_s
            t_extract = local_s + OFFSET_S
            if dur and t_extract > dur - 0.05:   # don't seek past end of segment
                t_extract = max(dur - 0.05, local_s)
            out = frames_dir / f"step_{n:02d}_s{global_s:.1f}.jpg"
            ok = extract_frame(display, t_extract, out)
            if not ok:
                print(f"  [seg {si} click {n}] frame extract FAILED at {t_extract:.2f}s")
                continue
            steps.append({
                "num": n,
                "t": round(global_s, 2),
                "x": round(xy[0], 4),
                "y": round(xy[1], 4),
                "text": caption_at(caption_segments, global_s),
                "frame": f"frames/{out.name}",
            })
            print(f"  step {n:02d}: seg{si} click @ {local_s:.1f}s "
                  f"(global {global_s:.1f}s) -> frame @ {t_extract:.1f}s  ({xy[0]:.2f},{xy[1]:.2f})")

        seg_offset += dur
    return steps


def render_html(title: str, steps: list[dict], has_captions: bool) -> str:
    cards = ""
    for s in steps:
        caption = html.escape(s["text"]) if s["text"] else f"Step {s['num']}"
        cards += f"""
    <div class="step">
      <div class="label">Step {s['num']} &middot; {s['t']}s</div>
      <p class="text">{caption}</p>
      <div class="shot">
        <img src="{s['frame']}" alt="Step {s['num']}" loading="lazy">
        <span class="marker" style="left:{s['x']*100:.2f}%;top:{s['y']*100:.2f}%"></span>
      </div>
    </div>"""

    note = "" if has_captions else (
        '<p class="note">No transcript in this recording (no mic/captions). '
        'Steps are click-driven only; record with a mic, or transcribe the Cap '
        'mic track via the WSL tool, to get narration + a bulleted summary.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>
  *,*::before,*::after{{box-sizing:border-box}}
  body{{font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;
       color:#222;max-width:880px;margin:40px auto;padding:0 24px 80px}}
  h1{{font-size:22px;color:#1A3A5C;margin:0 0 4px}}
  .meta{{font-size:12px;color:#999;margin:0 0 24px}}
  .note{{background:#FFF8E1;border-left:4px solid #E6C84A;border-radius:0 6px 6px 0;
        padding:10px 14px;font-size:13px;color:#4A3800;margin:0 0 24px}}
  .step{{border:1px solid #D0DFF0;border-radius:8px;padding:16px 18px;margin:0 0 18px}}
  .label{{font-size:11px;font-weight:700;color:#888;text-transform:uppercase;
         letter-spacing:.06em;margin:0 0 6px}}
  .text{{font-size:14px;color:#222;margin:0 0 12px}}
  .shot{{position:relative;display:inline-block;max-width:100%}}
  .shot img{{max-width:100%;border:1px solid #ddd;border-radius:4px;display:block}}
  .marker{{position:absolute;width:26px;height:26px;border:3px solid #D4730A;
          border-radius:50%;transform:translate(-50%,-50%);
          box-shadow:0 0 0 3px rgba(212,115,10,.25);pointer-events:none}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="meta">{len(steps)} steps &middot; ingested from a Cap Studio recording (cap_ingest.py)</p>
{note}
{cards}
</body></html>"""


def main() -> None:
    global OFFSET_S
    ap = argparse.ArgumentParser(description="Build an illustrated guide from a Cap .cap recording.")
    ap.add_argument("cap", help="Path to a .cap recording directory")
    ap.add_argument("--offset", type=float, default=OFFSET_S, help="Seconds after click to grab frame")
    ap.add_argument("--out", default=None, help="Output root (default: spike-output/cap)")
    ap.add_argument("--transcript", default=None,
                    help="Path to transcript JSON ({segments:[{start,end,text,words}]}) to use "
                         "instead of the recording's captions.json")
    args = ap.parse_args()

    OFFSET_S = args.offset

    cap_dir = Path(args.cap)
    if not cap_dir.exists():
        sys.exit(f"Path not found: {cap_dir}")

    meta = load_meta(cap_dir)
    segments = collect_segments(meta)
    title = meta.get("pretty_name", cap_dir.stem)

    out_root = Path(args.out) if args.out else (Path(__file__).parent / "spike-output" / "cap")
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in cap_dir.stem)[:60]
    out_dir = out_root / safe
    frames_dir = out_dir / "frames"

    print(f"Cap recording : {title}")
    print(f"Segments      : {len(segments)}")
    print(f"Output        : {out_dir}")
    print()

    # Transcript source: --transcript file > Cap captions.json > none
    if args.transcript:
        caption_segments = load_transcript_file(Path(args.transcript))
        print(f"Transcript    : {len(caption_segments)} segments (from {args.transcript})")
    else:
        caption_segments = load_captions(cap_dir)
        print(f"Transcript    : {len(caption_segments)} segments (Cap captions.json)"
              if caption_segments else "Transcript    : none (click-only)")
    print()

    steps = build_steps(cap_dir, segments, frames_dir, caption_segments)
    if not steps:
        sys.exit("No steps produced (no down-clicks found, or frame extraction failed).")

    has_caps = bool(caption_segments)
    out_dir.mkdir(parents=True, exist_ok=True)
    guide = out_dir / "guide.html"
    guide.write_text(render_html(title, steps, has_caps), encoding="utf-8")

    steps_json = out_dir / "steps.json"
    steps_json.write_text(json.dumps({"title": title, "steps": steps}, indent=2), encoding="utf-8")

    print()
    print(f"OK: {len(steps)} steps")
    print(f"   guide      -> {guide}  ({guide.stat().st_size // 1024}KB)")
    print(f"   steps.json -> {steps_json}")
    if not has_caps:
        print("   (no transcript - click-only; pass --transcript to add narration)")


if __name__ == "__main__":
    main()
