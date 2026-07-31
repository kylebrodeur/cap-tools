"""Read a Cap Studio .cap recording and extract clicks + frames.

Port of guide/spike/cap_ingest.py. Pure post-processor over the Cap on-disk
format. Reads recording-meta.json, cursor.json, display.mp4, and captions.json
to produce a steps.json and guide.html.

Video duration and frame extraction go through PyAV (the `av` package),
which ships FFmpeg statically compiled into the wheel — no system ffmpeg/
ffprobe binary, no PATH lookup, no risk of a Homebrew library-version
mismatch breaking guide generation (as system ffmpeg once did here).
"""

import json
import sys
from pathlib import Path
from typing import Optional

import av

# ── Config ────────────────────────────────────────────────────────────────────
OFFSET_S = 0.5       # seconds after click to grab frame
DEBOUNCE_MS = 400.0  # drop click within this ms of previous
DEBOUNCE_DIST = 0.01  # ...and within this normalized distance
JPEG_Q = 95           # Pillow JPEG quality (1=worst..95=best)


def _video_duration(path: Path) -> float:
    try:
        container = av.open(str(path))
        try:
            stream = container.streams.video[0]
            if stream.duration is not None:
                return float(stream.duration * stream.time_base)
            if container.duration is not None:
                return float(container.duration) / av.time_base
            return 0.0
        finally:
            container.close()
    except av.FFmpegError:
        return 0.0


def _load_meta(cap_dir: Path) -> dict:
    meta_path = cap_dir / "recording-meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Not a Cap recording: {cap_dir}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _collect_segments(meta: dict) -> list[dict]:
    """Return ordered segments from recording meta."""
    segs = meta.get("segments")
    if isinstance(segs, list) and segs and isinstance(segs[0], dict) and "display" in segs[0]:
        return [{
            "display": s["display"]["path"],
            "cursor": s.get("cursor"),
            "start_time": s["display"].get("start_time", 0.0),
            "fps": s["display"].get("fps", 30),
        } for s in segs]
    if "display" in meta:
        return [{
            "display": meta["display"]["path"],
            "cursor": meta.get("cursor"),
            "start_time": meta["display"].get("start_time", 0.0),
            "fps": meta["display"].get("fps", 30),
        }]
    raise ValueError("Unsupported recording format. Use Cap Studio mode.")


def _load_cursor(cap_dir: Path, rel: Optional[str]) -> tuple[list, list]:
    if not rel:
        return [], []
    p = cap_dir / rel
    if not p.exists():
        return [], []
    data = json.loads(p.read_text(encoding="utf-8"))
    clicks = sorted(data.get("clicks", []), key=lambda c: c.get("time_ms", 0))
    moves = sorted(data.get("moves", []), key=lambda m: m.get("time_ms", 0))
    return clicks, moves


def _meaningful_clicks(clicks: list) -> list:
    """Filter to down-presses only."""
    return [c for c in clicks if c.get("down")]


def _pos_at(moves: list, t_ms: float) -> Optional[tuple]:
    """Cursor (x,y) normalized at time t."""
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


def _extract_frame(display: Path, t_s: float, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    target_s = max(t_s, 0.0)
    try:
        container = av.open(str(display))
        try:
            stream = container.streams.video[0]
            container.seek(int(target_s / stream.time_base), stream=stream)
            frame = None
            for candidate in container.decode(stream):
                if candidate.pts is not None and float(candidate.pts * stream.time_base) >= target_s:
                    frame = candidate
                    break
                frame = candidate  # fall back to the last decodable frame
            if frame is None:
                return False
            frame.to_image().convert("RGB").save(out, format="JPEG", quality=JPEG_Q)
        finally:
            container.close()
    except av.FFmpegError:
        return False
    return out.exists()


def _load_captions(cap_dir: Path) -> list:
    p = cap_dir / "captions.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("segments", []) if isinstance(data, dict) else []


def _caption_at(segments: list, t_s: float) -> str:
    if not segments:
        return ""
    for s in segments:
        if s.get("start", 0) <= t_s <= s.get("end", 0):
            return s.get("text", "").strip()
    return min(segments, key=lambda s: abs(s.get("start", 0) - t_s)).get("text", "").strip()


def ingest(
    cap_path: str,
    out_dir: str,
    offset_s: float = OFFSET_S,
    transcript_path: Optional[str] = None,
    fmt: str = "both",
) -> dict:
    """Ingest a Cap Studio .cap recording and produce steps + guide.

    Args:
        cap_path: Path to .cap recording directory.
        out_dir: Output directory for frames and guide.
        offset_s: Seconds after click to grab frame.
        transcript_path: Optional path to external transcript JSON.
        fmt: "html", "md", or "both" — which guide file(s) to write.

    Returns:
        {"title": str, "steps": [...], "guide_html": str|None,
         "guide_md": str|None, "steps_json": str}
    """
    cap_dir = Path(cap_path)
    if not cap_dir.exists():
        raise FileNotFoundError(f"Path not found: {cap_dir}")

    meta = _load_meta(cap_dir)
    segments = _collect_segments(meta)
    title = meta.get("pretty_name", cap_dir.stem)

    out = Path(out_dir)
    frames_dir = out / "frames"

    # Transcript source
    if transcript_path:
        data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        caption_segments = data.get("segments", data if isinstance(data, list) else [])
    else:
        caption_segments = _load_captions(cap_dir)

    # Build steps
    steps = []
    seg_offset = 0.0
    n = 0

    for si, seg in enumerate(segments):
        display = cap_dir / seg["display"]
        dur = _video_duration(display)
        clicks, moves = _load_cursor(cap_dir, seg["cursor"])
        downs = _meaningful_clicks(clicks)

        last_t = -1e9
        last_xy = (-1.0, -1.0)
        for c in downs:
            t_ms = c["time_ms"]
            xy = _pos_at(moves, t_ms) or (0.5, 0.5)
            if ((t_ms - last_t) < DEBOUNCE_MS
                    and abs(xy[0] - last_xy[0]) < DEBOUNCE_DIST
                    and abs(xy[1] - last_xy[1]) < DEBOUNCE_DIST):
                continue
            last_t, last_xy = t_ms, xy

            n += 1
            local_s = t_ms / 1000.0
            global_s = seg_offset + local_s
            t_extract = local_s + offset_s
            if dur and t_extract > dur - 0.05:
                t_extract = max(dur - 0.05, local_s)

            frame_out = frames_dir / f"step_{n:02d}_s{global_s:.1f}.jpg"
            if not _extract_frame(display, t_extract, frame_out):
                continue

            steps.append({
                "num": n,
                "t": round(global_s, 2),
                "x": round(xy[0], 4),
                "y": round(xy[1], 4),
                "text": _caption_at(caption_segments, global_s),
                "frame": f"frames/{frame_out.name}",
            })

        seg_offset += dur

    if not steps:
        raise RuntimeError("No steps produced (no clicks found or frame extraction failed)")

    out.mkdir(parents=True, exist_ok=True)

    # Write steps.json
    steps_json_path = out / "steps.json"
    steps_data = {"title": title, "steps": steps}
    steps_json_path.write_text(json.dumps(steps_data, indent=2), encoding="utf-8")

    guide_html_path = None
    if fmt in ("html", "both"):
        guide_html_path = out / "guide.html"
        guide_html_path.write_text(_render_html(title, steps, bool(caption_segments)), encoding="utf-8")

    guide_md_path = None
    if fmt in ("md", "both"):
        guide_md_path = out / "guide.md"
        guide_md_path.write_text(_render_markdown(title, steps, bool(caption_segments)), encoding="utf-8")

    return {
        "title": title,
        "steps": steps,
        "guide_html": str(guide_html_path) if guide_html_path else None,
        "guide_md": str(guide_md_path) if guide_md_path else None,
        "steps_json": str(steps_json_path),
        "step_count": len(steps),
        "has_captions": bool(caption_segments),
    }


def _render_html(title: str, steps: list, has_captions: bool) -> str:
    import html as _html
    cards = ""
    for s in steps:
        caption = _html.escape(s["text"]) if s["text"] else f"Step {s['num']}"
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
        '<p class="note">No transcript in this recording. Steps are click-driven only.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_html.escape(title)}</title>
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
<h1>{_html.escape(title)}</h1>
<p class="meta">{len(steps)} steps &middot; ingested from a Cap Studio recording</p>
{note}
{cards}
</body></html>"""


def _render_markdown(title: str, steps: list, has_captions: bool) -> str:
    lines = [f"# {title}", "", f"{len(steps)} steps · ingested from a Cap Studio recording", ""]
    if not has_captions:
        lines += ["> No transcript in this recording. Steps are click-driven only.", ""]
    for s in steps:
        caption = s["text"] or f"Step {s['num']}"
        lines += [f"## Step {s['num']} · {s['t']}s", "", caption, "",
                  f"![Step {s['num']}]({s['frame']})", ""]
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Build an illustrated guide from a Cap .cap recording")
    ap.add_argument("cap", help="Path to .cap recording directory")
    ap.add_argument("--out", default=None, help="Output directory")
    ap.add_argument("--offset", type=float, default=OFFSET_S)
    ap.add_argument("--transcript", default=None, help="External transcript JSON")
    ap.add_argument("--format", default="both", choices=["html", "md", "both"])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out_dir = args.out or f"output/{Path(args.cap).stem}"
    result = ingest(args.cap, out_dir, args.offset, args.transcript, fmt=args.format)

    if args.json:
        print(json.dumps(result))
    else:
        print(f"OK: {result['step_count']} steps")
        if result["guide_html"]:
            print(f"   guide.html -> {result['guide_html']}")
        if result["guide_md"]:
            print(f"   guide.md   -> {result['guide_md']}")
        print(f"   steps.json -> {result['steps_json']}")


if __name__ == "__main__":
    main()
