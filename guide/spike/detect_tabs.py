#!/usr/bin/env python3
"""
detect_tabs.py — frame-level tab awareness via an Ollama vision model.

Two modes:
  • per-image:  classify the active tab in given screenshot files.
  • timeline:   sample a display.mp4 across time, crop the tab-bar strip, detect
                the active tab (or None if scrolled past the bar), and collapse
                into tab SPANS -> tabs.json. This is robust to scrolling.

Output spans feed:
  - structure.py  (group items by the REAL tab — fixes the missed Print tab)
  - build_walkthrough_doc.py (verify each item's screenshot is on the right tab)

Usage:
    # timeline (recommended):
    uv run spike/detect_tabs.py --video <display.mp4> --out tabs.json \
        [--interval 20] [--crop-frac 0.30] [--model gemma4:31b-cloud]
    # per-image spot check:
    uv run spike/detect_tabs.py <image.jpg|dir>... [--model gemma4:31b-cloud]

Config: OLLAMA_URL (default http://localhost:11434).
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = "gemma4:31b-cloud"

PROMPT = (
    "This is a screenshot of a desktop app with a horizontal tab bar near the top. "
    "Exactly one tab is visually active/highlighted. Which tab is active? "
    "Answer with ONLY one of these words: {tabs}. No other text."
)
PROMPT_TL = (
    "This is the top strip of a desktop app window. It MAY contain a horizontal "
    "tab bar where exactly one tab is highlighted. Which tab is active? Answer "
    "with ONLY one of these words: {tabs} — or the word None if no tab bar is "
    "visible in this image. No other text."
)


def _ask(image: Path, model: str, prompt: str) -> str:
    b64 = base64.b64encode(image.read_bytes()).decode()
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [b64]}],
        "think": False,
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["message"]["content"].strip()


def detect(image: Path, model: str, tabs: list[str]) -> str:
    content = _ask(image, model, PROMPT.format(tabs=", ".join(tabs)))
    low = content.lower()
    for t in tabs:
        if t.lower() in low:
            return t
    return content[:30] or "?"


def detect_or_none(image: Path, model: str, tabs: list[str]):
    content = _ask(image, model, PROMPT_TL.format(tabs=", ".join(tabs)))
    low = content.lower()
    if "none" in low or "no tab" in low:
        return None
    for t in tabs:
        if t.lower() in low:
            return t
    return None


def ffprobe_duration(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def extract_crop(video: Path, t: float, crop_frac: float, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-ss", f"{t + 0.3:.3f}", "-i", str(video), "-vframes", "1",
                    "-vf", f"crop=iw:ih*{crop_frac}:0:0", "-q:v", "2", "-y", str(out)],
                   capture_output=True)
    return out.exists()


def build_spans(samples: list[tuple], dur: float) -> list[dict]:
    """samples: [(t, tab|None)] in order. Collapse to spans; None inherits the
    current tab (scrolled frame). First known tab covers from 0."""
    spans, cur, seg_start = [], None, 0.0
    for t, tab in samples:
        if tab is None:
            continue
        if cur is None:
            cur, seg_start = tab, 0.0
        elif tab != cur:
            spans.append({"tab": cur, "start_s": round(seg_start, 1), "end_s": round(t, 1)})
            cur, seg_start = tab, t
    if cur is not None:
        spans.append({"tab": cur, "start_s": round(seg_start, 1), "end_s": round(dur, 1)})
    return spans


def tab_at(spans: list[dict], t: float) -> str | None:
    for s in spans:
        if s["start_s"] <= t < s["end_s"]:
            return s["tab"]
    return spans[-1]["tab"] if spans else None


def timeline(video: Path, model: str, tabs: list[str], interval: float,
             crop_frac: float, scratch: Path) -> tuple[list, list]:
    dur = ffprobe_duration(video)
    samples = []
    t = 0.0
    while t < dur:
        crop = scratch / f"f_{int(t):05d}.jpg"
        if extract_crop(video, t, crop_frac, crop):
            tab = detect_or_none(crop, model, tabs)
        else:
            tab = None
        samples.append((round(t, 1), tab))
        print(f"  {int(t//60)}:{int(t%60):02d}  ->  {tab or 'None'}", flush=True)
        t += interval
    return samples, build_spans(samples, dur)


def gather(paths: list[str]) -> list[Path]:
    out = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            out += sorted(pp.glob("*.jpg")) + sorted(pp.glob("*.png"))
        elif pp.exists():
            out.append(pp)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--tabs", default="Studio,Build,Print,Review")
    ap.add_argument("--video", default=None, help="timeline mode: a display.mp4")
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--crop-frac", type=float, default=0.30)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    tabs = [t.strip() for t in args.tabs.split(",")]

    if args.video:
        video = Path(args.video)
        out = Path(args.out or "tabs.json")
        scratch = out.parent / "_tabscan"
        print(f"Timeline tab scan: {args.model}, every {args.interval}s, crop {args.crop_frac}", flush=True)
        samples, spans = timeline(video, args.model, tabs, args.interval, args.crop_frac, scratch)
        out.write_text(json.dumps({
            "video": str(video), "model": args.model, "interval_s": args.interval,
            "spans": spans,
            "samples": [{"t": t, "tab": tab} for t, tab in samples],
        }, indent=2), encoding="utf-8")
        print("\nSPANS:")
        for s in spans:
            print(f"  {s['tab']:8s} {s['start_s']:7.1f} – {s['end_s']:7.1f}s")
        print(f"-> {out}")
        return

    imgs = gather(args.images)
    if not imgs:
        sys.exit("No images / no --video given.")
    print(f"Detecting tabs with {args.model} over {len(imgs)} frame(s)...", flush=True)
    result = {}
    for im in imgs:
        tab = detect(im, args.model, tabs)
        result[im.name] = tab
        print(f"  {im.name:28s} -> {tab}", flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"-> {args.out}")


if __name__ == "__main__":
    main()
