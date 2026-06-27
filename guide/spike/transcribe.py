#!/usr/bin/env python3
"""
transcribe.py — transcribe an audio/video file via the WSL transcription server.

The server (the user's tool) exposes provider switching and returns our exact
schema already: {"text": str, "segments": [{start, end, text, words:[{start,end,word}]}]}.
This replaces the faster-whisper stand-in (transcribe_local.py) for the real run.

Usage:
    uv run spike/transcribe.py <audio-or-video> <out transcript.json>
    uv run spike/transcribe.py <in> <out> --provider parakeet
    uv run spike/transcribe.py <in> <out> --provider faster-whisper --model medium

Server API (localhost:8000):
    POST /transcribe?provider=faster-whisper|parakeet|huggingface[&model=...]
    multipart field "file".  GET /health, GET /providers, POST /providers/switch.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = os.environ.get("TRANSCRIBE_URL", "http://localhost:8000")
AUDIO_FIELD = "file"


def post_file(url: str, file_path: Path, field: str) -> dict:
    boundary = "----GuideToolBoundary"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{file_path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body = head + file_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())


def normalize(resp: dict) -> dict:
    """Server already returns {text, segments:[{start,end,text,words}]}. Also
    tolerate a nested {whisper_result:{segments}} shape, just in case."""
    if "segments" in resp:
        segs = resp["segments"]
    elif "whisper_result" in resp:
        segs = resp["whisper_result"].get("segments", [])
    elif isinstance(resp, list):
        segs = resp
    else:
        raise ValueError(f"No segments in response keys: {list(resp.keys())}")
    duration = resp.get("duration") or (segs[-1].get("end") if segs else 0.0)
    return {"duration": duration, "text": resp.get("text", ""), "segments": segs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("out")
    ap.add_argument("--provider", default="faster-whisper",
                    help="faster-whisper | parakeet | huggingface")
    ap.add_argument("--model", default=None, help="model id (providers that support it)")
    args = ap.parse_args()

    audio = Path(args.audio)
    if not audio.exists():
        sys.exit(f"Audio not found: {audio}")

    q = {"provider": args.provider}
    if args.model:
        q["model"] = args.model
    url = f"{BASE}/transcribe?{urllib.parse.urlencode(q)}"

    mb = audio.stat().st_size / 1024 / 1024
    print(f"POST {url}\n  file: {audio.name} ({mb:.1f} MB)", flush=True)
    try:
        resp = post_file(url, audio, AUDIO_FIELD)
    except urllib.error.URLError as e:
        sys.exit(f"Request failed ({e}). Is the server up at {BASE}? (GET /health)")

    data = normalize(resp)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    words = sum(len(s.get("words", [])) for s in data["segments"])
    print(f"OK: {len(data['segments'])} segments, {words} words, "
          f"{data['duration']:.0f}s -> {out}")


if __name__ == "__main__":
    main()
