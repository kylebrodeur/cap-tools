# Refactor Plan — Unified cap-tools Python CLI

## Goal

Refactor the cap-tools project into a single unified Python CLI system that
handles both recording automation (from an internal reference project patterns) and guide
generation (from cap-whisper-doc spikes). One `capt` command, all Python.

---

## Module Map

```
capt/
├── __init__.py
├── cli.py                  # Click CLI entry point (6 subcommands)
├── cap_api.py              # Cap CLI wrapper (detach spawn, JSON parse, status)
├── config.py               # project-config.json builder + presets
├── zoom.py                 # Zoom segment builder from event timestamps
├── preflight.py            # G1-G6 gate checks
├── export.py               # cap export wrapper with progress
├── assemble.py             # ffmpeg manifest pipeline (port from assemble-video.py)
├── record/
│   ├── __init__.py
│   └── beat.py             # Beat orchestration: invoke Windows beat_runner, read results
├── guide/
│   ├── __init__.py
│   ├── ingest.py           # .cap → clicks + frames (from cap_ingest.py)
│   ├── structure.py        # Transcript → items.json via LLM (from structure.py)
│   ├── render.py           # items.json → HTML + MD + images (from build_walkthrough_doc.py)
│   ├── transcribe.py       # Audio transcription via WSL server (from transcribe.py)
│   └── detect_tabs.py      # Vision tab detection — companion (from detect_tabs.py)
└── templates/
    ├── config-demo.json    # Demo preset: wallpaper bg, padding, shadow, mellow cursor
    ├── config-clean.json   # Clean preset: black bg, no effects
    └── config-raw.json     # Raw preset: no bg, no camera, hide cursor

win/
├── beat_runner.py          # Windows-side: Python Playwright + Cap driver
├── requirements.txt        # playwright>=1.40
└── install.ps1             # One-time: pip install + playwright install chromium
```

---

## Module Details

### `capt/cli.py` — Unified CLI entry point
**What:** Click group with 6 subcommands: `record`, `guide`, `export`, `assemble`, `preflight`, `config`.
**Port from:** Current placeholder — flesh out with real implementations.
**Deps:** All other modules.

### `capt/cap_api.py` — Cap CLI wrapper
**What:** Wraps `cap-cli.exe` invocations. Handles detached spawn (temp file + sleep + parse), JSON parsing with depth-tracking fallback, status checks, screen discovery.
**Port from:** `docs/reference/record-preflight.py` (`_cap_bin`, `_cap_json` patterns) + `docs/reference/record-studio.cjs` (`capStartDetached`, `isRecording` patterns).
**Key functions:** `cap_json(args)`, `cap_start_detached(args)`, `cap_is_recording()`, `cap_get_primary_screen()`, `cap_project_config_get(path)`, `cap_project_config_set(path, cfg)`.

### `capt/config.py` — Project-config builder
**What:** Builds and writes `project-config.json`. Three presets: demo, clean, raw. Accepts overrides for zoom segments, background, cursor, spring physics.
**Port from:** `docs/PROJECT-CONFIG-SCHEMA.md` (schema reference) + `docs/ARCHITECTURE.md` (preset table).
**Key functions:** `build_config(preset, **overrides)`, `write_config(project_path, cfg)`.

### `capt/zoom.py` — Zoom segment builder
**What:** Generates `timeline.zoomSegments` from event timestamps. Merges overlapping segments.
**Port from:** Fresh implementation based on schema in `docs/PROJECT-CONFIG-SCHEMA.md`.
**Key functions:** `build_zoom_segments(events, amount=2.0, pre_s=0.5, hold_s=2.5, min_gap_s=1.0)`.

### `capt/preflight.py` — Gate checks
**What:** Six gates: cap-cli found, screen target, PowerShell reachable, URL reachable, output dir writable, Windows beat_runner ready.
**Port from:** `docs/reference/record-preflight.py` (G1-G5 pattern, generalize).
**Key functions:** `preflight(url, output_dir)` → `bool`.

### `capt/export.py` — Cap export wrapper
**What:** Wraps `cap export` with progress streaming (NDJSON).
**Port from:** Fresh implementation using `capt/cap_api.py`.
**Key functions:** `export_cap(project_path, output_path, fps=60, quality="maximum")`.

### `capt/assemble.py` — ffmpeg assembly
**What:** Manifest-driven ffmpeg pipeline: scale/pad segments, mix VO audio, burn captions, concat.
**Port from:** `docs/reference/assemble-video.py` (239 lines, fully generic — near-direct port).
**Key functions:** `assemble(manifest_path)`.

### `capt/record/beat.py` — Beat orchestration
**What:** Orchestrates a single beat: invoke Windows `beat_runner.py` via PowerShell, read results JSON from `/mnt/c/...`, apply polish, export.
**Port from:** Fresh implementation following `docs/ARCHITECTURE.md` beat cycle.
**Key functions:** `run_beat(name, url, output_dir, windows_dir, screen_id)`.

### `capt/guide/ingest.py` — .cap → clicks + frames
**What:** Reads `.cap` directory, extracts clicks from `cursor.json`, extracts frames from `display.mp4`, produces step guide.
**Port from:** `guide/spike/cap_ingest.py` (326 lines). Remove project-specific hardcoding, add `--json` output.
**Key functions:** `ingest(cap_dir, output_dir, offset_s=0.5)`.

### `capt/guide/structure.py` — Transcript → items.json
**What:** OpenAI-compatible format pass: transcript → analyzed items.json.
**Port from:** `guide/spike/structure.py` (252 lines). Generalize model/endpoint config.
**Key functions:** `structure(transcript_path, output_path, model=None, base_url=None)`.

### `capt/guide/render.py` — items.json → HTML + MD
**What:** Renders analyzed items into `index.html` + `index.md` + named images.
**Port from:** `guide/spike/build_walkthrough_doc.py` (245 lines). Externalize images (no base64).
**Key functions:** `render(items_path, display_mp4, output_dir)`.

### `capt/guide/transcribe.py` — Audio transcription
**What:** Transcribes audio via WSL server. Returns `{text, segments}`.
**Port from:** `guide/spike/transcribe.py` (97 lines). Near-direct port.
**Key functions:** `transcribe(audio_path, output_path, provider="faster-whisper")`.

### `capt/guide/detect_tabs.py` — Vision tab detection
**What:** Frame-level tab detection via Ollama vision model. Companion tool.
**Port from:** `guide/spike/detect_tabs.py` (198 lines). Keep as optional extra.
**Key functions:** `detect_tabs(display_mp4, output_path, model=None)`.

### `win/beat_runner.py` — Windows-side driver
**What:** Python Playwright on Windows. Launches Chrome natively, starts/stops Cap, drives beat steps, collects timestamps, writes results JSON.
**Port from:** Fresh implementation following `docs/ARCHITECTURE.md` beat-runner spec + a companion project Playwright patterns (`--start-maximized`, optional CDP port).
**Key functions:** `run_beat(beat_name, url, output_dir, screen_id)`.

---

## Dependencies

```
cli.py
├── record/beat.py → cap_api.py, zoom.py, config.py, export.py
│   └── win/beat_runner.py (invoked via PowerShell, runs on Windows)
├── guide/
│   ├── ingest.py → cap_api.py (for project validate)
│   ├── transcribe.py (standalone)
│   ├── structure.py (standalone, uses OpenAI-compatible endpoint)
│   └── render.py (standalone, uses ffmpeg)
├── export.py → cap_api.py
├── assemble.py (standalone, uses ffmpeg)
├── preflight.py → cap_api.py
└── config.py → cap_api.py
```

---

## Implementation Order

### Step 1: Foundation modules (no external deps beyond stdlib)
1. `capt/cap_api.py` — Cap CLI wrapper (port from record-preflight.py + record-studio.cjs patterns)
2. `capt/config.py` — Project-config builder with presets
3. `capt/zoom.py` — Zoom segment builder

### Step 2: Guide pipeline (port from spike scripts)
4. `capt/guide/transcribe.py` — Near-direct port from guide/spike/transcribe.py
5. `capt/guide/ingest.py` — Port from guide/spike/cap_ingest.py, generalize
6. `capt/guide/structure.py` — Port from guide/spike/structure.py, generalize
7. `capt/guide/render.py` — Port from guide/spike/build_walkthrough_doc.py, externalize images
8. `capt/guide/detect_tabs.py` — Port from guide/spike/detect_tabs.py (companion)

### Step 3: Record pipeline
9. `win/beat_runner.py` — Windows-side Python Playwright + Cap driver
10. `capt/record/beat.py` — Beat orchestration (WSL side)
11. `capt/preflight.py` — Gate checks (port from record-preflight.py)

### Step 4: Export & Assembly
12. `capt/export.py` — Cap export wrapper
13. `capt/assemble.py` — Port from assemble-video.py

### Step 5: CLI integration
14. `capt/cli.py` — Wire all subcommands to real implementations
15. `pyproject.toml` — Update deps (add `httpx` or `requests` for URL checks)
16. Templates: `capt/templates/config-*.json`

### Step 6: Docs & cleanup
17. Update `README.md`, `docs/README.md`
18. Update `skills/cap-cli/SKILL.md`
19. Archive old `guide/spike/` scripts (move to `guide/_archive/`)

---

## Port vs Fresh Summary

| Module | Port from | Effort |
|---|---|---|
| `capt/cap_api.py` | record-preflight.py patterns + record-studio.cjs patterns | Medium — new module, known patterns |
| `capt/config.py` | PROJECT-CONFIG-SCHEMA.md reference | Low — JSON builder |
| `capt/zoom.py` | Fresh | Low — simple math |
| `capt/preflight.py` | record-preflight.py | Low — generalize existing |
| `capt/export.py` | Fresh (thin cap_api wrapper) | Low |
| `capt/assemble.py` | assemble-video.py | Low — near-direct port |
| `capt/record/beat.py` | Fresh (ARCHITECTURE.md spec) | Medium — orchestration logic |
| `capt/guide/ingest.py` | cap_ingest.py | Medium — generalize, add --json |
| `capt/guide/structure.py` | structure.py | Low — generalize config |
| `capt/guide/render.py` | build_walkthrough_doc.py | Medium — externalize images |
| `capt/guide/transcribe.py` | transcribe.py | Low — near-direct port |
| `capt/guide/detect_tabs.py` | detect_tabs.py | Low — near-direct port |
| `win/beat_runner.py` | Fresh (ARCHITECTURE.md + a companion project patterns) | High — new module, cross-platform |
| `capt/cli.py` | Current placeholder | Medium — wire implementations |
