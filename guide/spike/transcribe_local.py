#!/usr/bin/env python3
"""
transcribe_local.py — local faster-whisper transcription (stand-in for the WSL tool).

A self-contained fallback so the pipeline can run end-to-end before the WSL
transcription endpoint is wired. Produces the project's transcript schema
(word-level), so cap_ingest.py / assemble.py consume it unchanged.

Usage (deps fetched on the fly; pin 3.12 to avoid 3.14 wheel gaps):
    uv run --python 3.12 --with faster-whisper python spike/transcribe_local.py \
        "<audio-or-video>" "<out transcript.json>" [model]

Default model: small.en  (good accuracy/speed on CPU int8).
"""
import json
import sys
from pathlib import Path

from faster_whisper import WhisperModel


def main() -> None:
    audio = sys.argv[1]
    out = Path(sys.argv[2])
    model_name = sys.argv[3] if len(sys.argv) > 3 else "small.en"
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading model: {model_name} (cpu/int8)...", flush=True)
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    print(f"Transcribing: {audio}", flush=True)
    segments, info = model.transcribe(
        audio,
        language="en",
        word_timestamps=True,
        vad_filter=True,  # skip long silences in an 18-min walkthrough
    )

    segs = []
    for s in segments:
        words = [
            {"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3)}
            for w in (s.words or [])
        ]
        segs.append({
            "id": str(s.id),
            "start": round(s.start, 3),
            "end": round(s.end, 3),
            "text": s.text.strip(),
            "words": words,
        })
        # progress ping every ~30s of audio
        if int(s.start) % 30 == 0:
            print(f"  ...{s.start:6.1f}s  {s.text.strip()[:70]}", flush=True)

    out.write_text(
        json.dumps({"duration": info.duration, "segments": segs}, indent=2),
        encoding="utf-8",
    )
    print(f"OK: {len(segs)} segments -> {out}", flush=True)


if __name__ == "__main__":
    main()
