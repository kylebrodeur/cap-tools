"""Transcribe audio via WSL transcription server.

Port of guide/spike/transcribe.py. Sends audio to a local transcription server
and returns word-level segments.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("TRANSCRIBE_URL", "http://localhost:8000")


def transcribe(
    audio_path: str,
    provider: str = "faster-whisper",
    model: str = None,
    base_url: str = None,
) -> dict:
    """Transcribe an audio/video file.

    Args:
        audio_path: Path to audio or video file.
        provider: Transcription provider (faster-whisper, parakeet, huggingface).
        model: Model ID (provider-dependent).
        base_url: Override transcription server URL.

    Returns:
        {"duration": float, "text": str, "segments": [{start, end, text, words}]}
    """
    url_base = base_url or BASE_URL
    audio = Path(audio_path)
    if not audio.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    q = {"provider": provider}
    if model:
        q["model"] = model
    url = f"{url_base}/transcribe?{urllib.parse.urlencode(q)}"

    boundary = "----CapToolsBoundary"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{audio.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body = head + audio.read_bytes() + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=1800) as r:
        resp = json.loads(r.read())

    # Normalize response shape
    if "segments" in resp:
        segs = resp["segments"]
    elif "whisper_result" in resp:
        segs = resp["whisper_result"].get("segments", [])
    elif isinstance(resp, list):
        segs = resp
    else:
        raise ValueError(f"No segments in response: {list(resp.keys())}")

    duration = resp.get("duration") or (segs[-1].get("end") if segs else 0.0)
    return {"duration": duration, "text": resp.get("text", ""), "segments": segs}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Transcribe audio via WSL server")
    ap.add_argument("audio", help="Path to audio/video file")
    ap.add_argument("out", help="Output transcript JSON path")
    ap.add_argument("--provider", default="faster-whisper")
    ap.add_argument("--model", default=None)
    ap.add_argument("--url", default=None, help="Override server URL")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    data = transcribe(args.audio, args.provider, args.model, args.url)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    words = sum(len(s.get("words", [])) for s in data["segments"])
    msg = f"OK: {len(data['segments'])} segments, {words} words, {data['duration']:.0f}s -> {out}"
    if args.json:
        print(json.dumps({"status": "completed", "segments": len(data["segments"]),
                          "words": words, "duration": data["duration"], "path": str(out)}))
    else:
        print(msg)


if __name__ == "__main__":
    main()
