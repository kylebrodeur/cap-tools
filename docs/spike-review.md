# Spike Review — What to keep vs refactor

Review of `guide/spike/` scripts. Determines what forms the basis of the
unified system vs what gets archived.

---

## Core pipeline (keep, refactor into unified `cap guide`)

These four scripts form the deterministic guide generation pipeline. They
should be refactored into a single `capguide` module with a clean CLI.

| Script | Lines | Role | Refactor into |
|---|---|---|---|
| `cap_ingest.py` | 326 | Read `.cap` dir → clicks + frames → `guide.html` | `capguide/ingest.py` — step derivation + frame extraction |
| `structure.py` | 252 | Transcript → analyzed `items.json` via LLM format pass | `capguide/structure.py` — optional `--ai` step-text |
| `build_walkthrough_doc.py` | 245 | `items.json` → `index.html` + `index.md` + named images | `capguide/render.py` — HTML + MD renderer |
| `transcribe.py` | 97 | Transcribe audio via WSL server | `capguide/transcribe.py` — caption source |

**Pipeline order:** `cap_ingest` → `transcribe` → `structure` → `build_walkthrough_doc`

---

## Companion tools (keep, separate from core)

These are useful but app-specific or optional. Keep as companion utilities.

| Script | Lines | Role | Why separate |
|---|---|---|---|
| `detect_tabs.py` | 198 | Vision-based tab detection (app-specific) | Only needed for multi-tab apps; uses vision model |
| `transcribe_local.py` | 64 | Local faster-whisper fallback | Stand-in when WSL server unavailable |

---

## Archived (superseded)

These were early experiments or standalone tools superseded by Cap integration.

| Script | Lines | Why archived |
|---|---|---|
| `assemble.py` | 185 | Early events+transcript+frames → guide. Superseded by `cap_ingest` + `build_walkthrough_doc`. |
| `record.py` | 325 | Standalone Windows recorder (gdigrab + pynput). Superseded by Cap. |
| `extract_frames.py` | 88 | ffmpeg frame extraction. Both `cap_ingest` and `build_walkthrough_doc` do this inline now. |

---

## Reference (keep as-is)

| File | Role |
|---|---|
| `SPIKE_IMPROVEMENT_BRIEF.md` | Phased plan + authoritative `.cap` format reference (§7.1) |

---

## Refactor target: `capguide` module

```
guide/capguide/
├── __init__.py
├── ingest.py          # cap_ingest.py → step derivation + frame extraction
├── structure.py       # structure.py → optional --ai format pass
├── render.py          # build_walkthrough_doc.py → HTML + MD renderer
├── transcribe.py      # transcribe.py → caption source
├── cli.py             # unified CLI: capguide <project.cap> [--ai] [--format]
└── companion/
    ├── detect_tabs.py  # app-specific tab detection
    └── transcribe_local.py  # local fallback
```
