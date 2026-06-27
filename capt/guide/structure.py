"""Format pass: transcript → analyzed items.json via LLM.

Port of guide/spike/structure.py. Sends a condensed transcript to an
OpenAI-compatible endpoint and produces a structured item breakdown.
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Optional

BASE_URL = os.environ.get("STRUCTURE_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.environ.get("STRUCTURE_API_KEY", "")
MODEL = os.environ.get("STRUCTURE_MODEL", "gemma4:12b")

SCHEMA_HINT = """Output ONLY a JSON object (no prose, no code fences) with exactly this shape:
{
  "title": str,
  "recording": str,
  "summary": str,
  "globals": [str, ...],
  "contradictions": [{"title": str, "resolution": str}, ...],
  "open_questions": [{"id": "oq-1", "q": str, "ref": str}, ...],
  "sections": [
    {"tab": str, "range": "M:SS - M:SS", "items": [
      {"id": "tab-01", "t": <seconds:int>, "title": str,
       "said": str, "decision": str, "flag": str|null}
    ]}
  ]
}"""

SYSTEM_PROMPT = f"""You analyze a narrated UI/UX walkthrough transcript and produce a structured breakdown.
The speaker walks through an app and requests changes. Your job:
- Split the narration into DISCRETE change-request items, in order.
- Group items by the TAB/section the speaker is on.
- For each item: a short title, `said` (faithful paraphrase), `decision` (clear/actionable), `t` = timestamp in SECONDS.
- Give items ids like "tab-01", zero-padded, per tab.
- Collect cross-tab rules into `globals`.
- Capture self-corrections in `contradictions` resolved to FINAL decision.
- Capture undecided items in `open_questions`.
Be thorough — capture every distinct request. {SCHEMA_HINT}"""

_STOP = set("the a an to of and or is it this that these those we you i be in on for with at "
            "as so but if then there here have has had do does will would should can could "
            "make made move add this thing stuff just like also into not no out up down".split())


def _condense(transcript_path: Path) -> str:
    d = json.loads(transcript_path.read_text(encoding="utf-8"))
    segs = d.get("segments", d if isinstance(d, list) else [])
    lines = []
    for s in segs:
        st = s.get("start", 0)
        lines.append(f"[{int(st // 60)}:{int(st % 60):02d}] {s.get('text', '').strip()}")
    return "\n".join(lines)


def _chat(messages: list[dict], model: str, base_url: str = None) -> str:
    url_base = (base_url or BASE_URL).rstrip("/")
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    # Try Ollama native API first
    if url_base.endswith("/v1"):
        ollama = url_base[:-3]
        body = json.dumps({
            "model": model, "messages": messages,
            "think": False, "format": "json",
            "options": {"temperature": 0.2, "num_ctx": 32768, "num_predict": 16384},
            "stream": False,
        }).encode()
        req = urllib.request.Request(f"{ollama}/api/chat", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())["message"]["content"]

    # Generic OpenAI-compatible
    body = json.dumps({
        "model": model, "messages": messages, "temperature": 0.2,
        "max_tokens": 16384, "response_format": {"type": "json_object"}, "stream": False,
    }).encode()
    req = urllib.request.Request(f"{url_base}/chat/completions", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    return json.loads(text)


def _toks(s: str) -> set:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if len(w) > 3 and w not in _STOP}


def _anchor_timestamps(data: dict, transcript_path: Path) -> dict:
    """Ground each item's t in the transcript by token overlap."""
    d = json.loads(transcript_path.read_text(encoding="utf-8"))
    segs = d.get("segments", d if isinstance(d, list) else [])
    segments = [(float(s.get("start", 0)), _toks(s.get("text", ""))) for s in segs]
    if not segments:
        return data
    for sec in data.get("sections", []):
        for it in sec.get("items", []):
            itoks = _toks(f"{it.get('title', '')} {it.get('said', '')}")
            if not itoks:
                continue
            best_start, best_score = None, 0
            for start, stoks in segments:
                score = len(itoks & stoks)
                if score > best_score:
                    best_score, best_start = score, start
            if best_start is not None and best_score >= 2:
                it["t"] = int(round(best_start))
    return data


def structure(
    transcript_path: str,
    out_path: str,
    model: str = None,
    title: str = "Walkthrough — Item Breakdown",
    recording: str = "",
    base_url: str = None,
) -> dict:
    """Run the format pass: transcript → analyzed items.json.

    Args:
        transcript_path: Path to transcript JSON.
        out_path: Output path for items.json.
        model: LLM model to use.
        title: Title for the breakdown.
        recording: Recording name.
        base_url: Override LLM endpoint URL.

    Returns:
        The parsed items data dict.
    """
    m = model or MODEL
    transcript = _condense(Path(transcript_path))

    user = f"Title: {title}\nRecording: {recording}\n\nTRANSCRIPT (timestamps are [M:SS]):\n{transcript}"
    content = _chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
        m, base_url,
    )

    try:
        data = _parse_json(content)
    except Exception as e:
        raw_path = Path(out_path).with_suffix(".raw.txt")
        raw_path.write_text(content, encoding="utf-8")
        raise RuntimeError(f"Model output was not valid JSON: {e}. Raw saved to {raw_path}")

    if title and not data.get("title"):
        data["title"] = title
    if recording and not data.get("recording"):
        data["recording"] = recording

    data = _anchor_timestamps(data, Path(transcript_path))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    secs = data.get("sections", [])
    total = sum(len(s.get("items", [])) for s in secs)
    return {"items": total, "sections": len(secs), "path": str(out), "data": data}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Format pass: transcript → analyzed items.json")
    ap.add_argument("transcript", help="Path to transcript JSON")
    ap.add_argument("out", help="Output items.json path")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--title", default="Walkthrough — Item Breakdown")
    ap.add_argument("--recording", default="")
    ap.add_argument("--url", default=None, help="Override LLM endpoint")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = structure(args.transcript, args.out, args.model,
                       args.title, args.recording, args.url)
    if args.json:
        print(json.dumps({"status": "completed", "items": result["items"],
                          "sections": result["sections"], "path": result["path"]}))
    else:
        print(f"OK: {result['items']} items in {result['sections']} sections -> {result['path']}")


if __name__ == "__main__":
    main()
