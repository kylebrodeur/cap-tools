#!/usr/bin/env python3
"""
structure.py — the "format pass": transcript -> analyzed items.json, via an
OpenAI-compatible chat endpoint (Ollama by default; any BYOK endpoint).

This is the reproducible replacement for hand-authoring items.json. Same
recording in -> items.json out, no human in the loop. Output is then
agent-reviewed.

Usage:
    uv run spike/structure.py <transcript.json> <out items.json> [--model gemma4:12b]

Config via env: STRUCTURE_BASE_URL (default http://localhost:11434/v1),
STRUCTURE_API_KEY (optional, BYOK), STRUCTURE_MODEL.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("STRUCTURE_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.environ.get("STRUCTURE_API_KEY", "")
MODEL = os.environ.get("STRUCTURE_MODEL", "gemma4:12b")

SCHEMA_HINT = """Output ONLY a JSON object (no prose, no code fences) with exactly this shape:
{
  "title": str,
  "recording": str,
  "summary": str,
  "globals": [str, ...],                      // cross-tab rules stated by the speaker
  "contradictions": [{"title": str, "resolution": str}, ...],  // self-corrections, resolved to the FINAL word
  "open_questions": [{"id": "oq-1", "q": str, "ref": str}, ...],// things left genuinely undecided
  "sections": [
    {"tab": str, "range": "M:SS – M:SS", "items": [
      {"id": "studio-01", "t": <seconds:int>, "title": str,
       "said": str,        // faithful paraphrase of what the speaker asked for
       "decision": str,    // the clear, actionable decision
       "flag": str|null}   // note contradictions/open-questions, else null
    ]}
  ]
}"""

SYSTEM = f"""You analyze a narrated UI/UX walkthrough transcript and produce a structured breakdown.
The speaker walks through an app tab by tab and requests changes. Your job:
- Split the narration into DISCRETE change-request items, in order.
- Group items by the TAB the speaker is on. Tab names appear in the narration when the speaker switches ("studio tab", "build tab", "review tab"); infer the tab between switches. NOTE: the speaker may not announce every tab.
- For each item: a short title, `said` (faithful paraphrase), `decision` (clear/actionable), `t` = the timestamp in SECONDS derived from the [M:SS] tag where it's discussed.
- Give items ids like "<tab>-01" (e.g. studio-01, build-03), zero-padded, per tab.
- Collect cross-tab rules (e.g. "no emojis", consistent button placement, shared footers) into `globals`.
- When the speaker reverses themselves, capture it in `contradictions` resolved to their FINAL decision (and set the earlier item's `flag`).
- When the speaker explicitly leaves something undecided ("not sure", "button or a tab", "maybe"), add an `open_questions` entry and flag the item.
Be thorough — capture every distinct request. {SCHEMA_HINT}"""


def condense(transcript_path: Path) -> str:
    d = json.loads(transcript_path.read_text(encoding="utf-8"))
    segs = d.get("segments", d if isinstance(d, list) else [])
    lines = []
    for s in segs:
        st = s.get("start", 0)
        lines.append(f"[{int(st//60)}:{int(st%60):02d}] {s.get('text','').strip()}")
    return "\n".join(lines)


def chat(messages: list[dict], model: str) -> str:
    """Generate JSON. Uses Ollama's native /api/chat when pointed at Ollama
    (so we can disable 'thinking', which otherwise eats the token budget and
    returns empty content); falls back to the OpenAI-compatible /v1 endpoint."""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    base = BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        ollama = base[:-3]  # native API is the host root
        body = json.dumps({
            "model": model,
            "messages": messages,
            "think": False,            # disable gemma reasoning -> content isn't starved
            "format": "json",          # constrain output to a JSON object
            "options": {"temperature": 0.2, "num_ctx": 32768, "num_predict": 16384},
            "stream": False,
        }).encode()
        req = urllib.request.Request(f"{ollama}/api/chat", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())["message"]["content"]

    # Generic OpenAI-compatible endpoint
    body = json.dumps({
        "model": model, "messages": messages, "temperature": 0.2,
        "max_tokens": 16384, "response_format": {"type": "json_object"}, "stream": False,
    }).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    # grab the outermost {...} if the model wrapped it
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    return json.loads(text)


def load_spans(path) -> list:
    if not path:
        return []
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return d.get("spans", []) if isinstance(d, dict) else d


def tab_at(spans: list, t: float):
    for s in spans:
        if s["start_s"] <= t < s["end_s"]:
            return s["tab"]
    return spans[-1]["tab"] if spans else None


def _mmss(x: float) -> str:
    return f"{int(x // 60)}:{int(x % 60):02d}"


_STOP = set("the a an to of and or is it this that these those we you i be in on for with at "
            "as so but if then there here have has had do does will would should can could "
            "make made move add this thing stuff just like also into not no out up down".split())


def _toks(s: str) -> set:
    return {w for w in re.findall(r"[a-z]+", (s or "").lower()) if len(w) > 3 and w not in _STOP}


def load_segments(transcript_path: Path) -> list:
    d = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    segs = d.get("segments", d if isinstance(d, list) else [])
    return [(float(s.get("start", 0)), _toks(s.get("text", ""))) for s in segs]


def anchor_timestamps(data: dict, segments: list) -> dict:
    """Ground each item's `t` in the transcript: pick the segment whose words
    best overlap the item, instead of trusting the model's (drift-prone) `t`."""
    if not segments:
        return data
    for sec in data.get("sections", []):
        for it in sec.get("items", []):
            itoks = _toks(f"{it.get('title','')} {it.get('said','')}")
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


def regroup_by_tabs(data: dict, spans: list) -> dict:
    """Override the model's tab grouping with the detected tab SPANS: re-bucket
    every item by its timestamp, in span order, and renumber ids per tab."""
    items = [it for sec in data.get("sections", []) for it in sec.get("items", [])]
    order, rng = [], {}
    for s in spans:
        if s["tab"] not in order:
            order.append(s["tab"])
        lo, hi = s["start_s"], s["end_s"]
        rng[s["tab"]] = (min(rng.get(s["tab"], (lo, hi))[0], lo),
                         max(rng.get(s["tab"], (lo, hi))[1], hi))
    for it in items:
        it["_tab"] = tab_at(spans, float(it.get("t", 0))) or "Unassigned"

    sections = []
    for tab in order + ["Unassigned"]:
        group = sorted((it for it in items if it.get("_tab") == tab),
                       key=lambda it: float(it.get("t", 0)))
        if not group:
            continue
        prefix = tab.split()[0].lower()
        for i, it in enumerate(group, 1):
            it["id"] = f"{prefix}-{i:02d}"
            it.pop("_tab", None)
        lo, hi = rng.get(tab, (0, 0))
        label = tab if tab.endswith("Tab") or tab == "Unassigned" else f"{tab} Tab"
        sections.append({"tab": label,
                         "range": "" if tab == "Unassigned" else f"{_mmss(lo)} – {_mmss(hi)}",
                         "items": group})
    data["sections"] = sections
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("out")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--title", default="Walkthrough — Item Breakdown")
    ap.add_argument("--recording", default="")
    ap.add_argument("--tabs", default=None, help="tabs.json from detect_tabs.py timeline mode")
    args = ap.parse_args()

    transcript = condense(Path(args.transcript))
    print(f"Transcript: {transcript.count(chr(10))+1} lines -> {args.model} @ {BASE_URL}", flush=True)

    spans = load_spans(args.tabs)
    tabctx = ""
    if spans:
        lines = "\n".join(f"  {s['tab']}: {_mmss(s['start_s'])}–{_mmss(s['end_s'])}" for s in spans)
        tabctx = ("\n\nTAB TIMELINE (the speaker is on these tabs during these times — "
                  f"group items by this, not by guesswork):\n{lines}")
        print(f"Tabs: {len(spans)} spans loaded from {args.tabs}", flush=True)

    user = (f"Title: {args.title}\nRecording: {args.recording}{tabctx}\n\n"
            f"TRANSCRIPT (timestamps are [M:SS]):\n{transcript}")
    content = chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        args.model,
    )
    try:
        data = parse_json(content)
    except Exception as e:
        raw = Path(args.out).with_suffix(".raw.txt")
        raw.write_text(content, encoding="utf-8")
        sys.exit(f"Model output was not valid JSON ({e}). Raw saved to {raw}")

    if args.title and not data.get("title"):
        data["title"] = args.title
    if args.recording and not data.get("recording"):
        data["recording"] = args.recording
    data = anchor_timestamps(data, load_segments(Path(args.transcript)))  # ground t in transcript
    if spans:
        data = regroup_by_tabs(data, spans)   # override model grouping with detected spans

    Path(args.out).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    secs = data.get("sections", [])
    total = sum(len(s.get("items", [])) for s in secs)
    print(f"OK: {total} items in {len(secs)} sections "
          f"({', '.join(s.get('tab','?')+':'+str(len(s.get('items',[]))) for s in secs)})")
    print(f"    globals={len(data.get('globals',[]))} "
          f"contradictions={len(data.get('contradictions',[]))} "
          f"open_questions={len(data.get('open_questions',[]))}")
    print(f"    -> {args.out}")


if __name__ == "__main__":
    main()
