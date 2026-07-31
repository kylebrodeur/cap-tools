# Guide Tool

Turn a screen recording of a workflow into a clean, illustrated guide —
**bulleted summary of what was said + a crisp screenshot per step** — that can
be pasted into an AI model or exported as a file. Think *Wispr Flow, but for
screen workflows*.

> **Status (June 2026):** Spike phase. The click → screenshot → illustrated
> guide pipeline is **built and validated on real recordings**. Narration →
> bulleted summary is wired but blocked on one input (the local transcription
> endpoint). See [Current status](#current-status).

---

## The idea in one paragraph

You record yourself doing a workflow while narrating it. The tool pairs **what
you clicked** (timestamped click events) with **what you said** (a transcript)
and **what was on screen** (a screenshot at each click), then assembles a
step-by-step guide. The AI is invisible: it does a single "format pass"
(transcript → clean bullets), not a chat. Output is HTML-first; Markdown / docx
are generated from it.

## How we get the data — consume Cap, don't rebuild the recorder

The big architectural decision: **[Cap](https://cap.so) (cap.so) already
records everything we need**, and in high quality. Cap is open-source
(Tauri + Rust), and its **Studio mode** recordings are a documented on-disk
format (`.cap` directory) containing:

- `display.mp4` — high-quality screen video, per segment
- a **separate clean mic track** (`audio-input.ogg`, Opus) — ideal to transcribe
- `cursor.json` — **click events** (`time_ms`, `down`, button, modifiers) +
  cursor move trail (`x`/`y` **normalized 0..1** to the display)
- optional `captions.json` — word-level transcript (Cap's, when present)
- `keyboard.bin`, `screenshots/`, cursor images

So this project is a **pure post-processor** over a `.cap` directory — no
capture code of its own to maintain. The full format is documented in
[`spike/SPIKE_IMPROVEMENT_BRIEF.md` §7.1](spike/SPIKE_IMPROVEMENT_BRIEF.md).

> Cap's *Instant* mode is the low-quality fast-share path; **use Studio mode**.
> Cap's transcription is cloud-only, so we always transcribe the mic track
> ourselves via the local WSL tool.

## Pipeline

```
Cap Studio .cap dir
  ├─ cursor.json   ──► meaningful clicks (down, debounced)
  ├─ display.mp4   ──► screenshot per click (at click + 0.5s), CSS click marker
  ├─ audio-input.ogg ─► WSL transcription tool ──► transcript (word-level)
  └─ (join on timeline)
         └──► format pass (single OpenAI-compatible call, fixed prompt)
                └──► guide.html  (bulleted summary + illustrated steps)
                       └──► export: Markdown / docx (from HTML)
```

## Repository layout

```
guide-tool/
├── README.md              ← you are here
├── DECISIONS.md           ← decision log D1–D10 (why the architecture is what it is)
├── ROADMAP.md             ← current state + future proposals / backlog
├── PRODUCTIZATION.md      ← market landscape + productization strategy (draft)
├── CAP-UPSTREAM-PROPOSAL.md ← tightened system as a `cap doc` upstream RFC (draft)
├── UPSTREAM-AGENT-BRIEF.md  ← hand-off prompt: tighten the impl + prep upstream materials
├── ARCHITECTURE.md        ← earlier (pre-Cap) design notes; still useful context
├── guide.py               ← project-management CLI (sessions, context, build)
├── mcp_server.py          ← MCP server exposing project state to Claude
├── config.json            ← global preferences (author, branding, style)
├── pyproject.toml         ← uv-managed deps
├── spike/                 ← the data-pipeline spike (this phase's work)
│   ├── transcribe.py      ← transcribe via the WSL server (?provider=) — ✅ wired
│   ├── transcribe_local.py← local faster-whisper — offline stand-in / fallback
│   ├── cap_ingest.py      ← .cap → frames + steps.json + click-guide   ★ validated
│   ├── build_walkthrough_doc.py ← items.json → index.html + index.md + named images (+--cursor regions)
│   ├── record.py          ← standalone Windows recorder (gdigrab + pynput) — fallback
│   ├── extract_frames.py  ← ffmpeg frame extraction (click + 0.5s)
│   ├── assemble.py        ← early events+transcript+frames → guide.html
│   ├── SPIKE_IMPROVEMENT_BRIEF.md  ← phased plan + full Cap .cap format ref
│   └── spike-output/      ← generated artifacts (gitignored)
├── doc-builder/docs/      ← product concept + spike plan (HTML) + pipeline-audit-2026-06-14.md
└── projects/              ← guide.py working projects (media gitignored)
```

## Runtime & setup

- **OS split (intentional):** the standalone `record.py`/`extract_frames.py`
  are **Windows-native** (gdigrab, ffmpeg via Scoop). Transcription runs in
  **WSL2** (CUDA); the AI format pass hits an **OpenAI-compatible** endpoint
  (the WSL tool, or local Ollama). They talk over **localhost HTTP**.
  `cap_ingest.py` itself is cross-platform Python.
- **Toolchain:** [uv](https://docs.astral.sh/uv/). ffmpeg on PATH.

```bash
# deps
uv sync                       # or: uv add pynput jinja2 openai
# ffmpeg (Windows): scoop install ffmpeg

# ingest a Cap Studio recording into an illustrated guide
uv run spike/cap_ingest.py "C:/path/to/recording.cap"
#   → spike/spike-output/cap/<name>/guide.html
```

## Productization direction

This is naturally a **CLI + MCP "Cap add-on"**, not a GUI app — it's a pure
`.cap → guide` transform. Planned shape:

- **CLI core** — `cap_ingest.py` (already that).
- **MCP layer** (on `mcp_server.py`) — `list_recordings`, `ingest`,
  `get_steps` (structured JSON an agent can edit), `render_guide(format)`.
  This is what makes it pair with an agent harness: the agent reasons over
  structured steps, not pixels.
- **Add-on behavior** — optionally watch `%APPDATA%/so.cap.desktop/recordings`
  and auto-draft a guide per new recording.

See [DECISIONS.md](DECISIONS.md) for the full rationale and
[`spike/SPIKE_IMPROVEMENT_BRIEF.md`](spike/SPIKE_IMPROVEMENT_BRIEF.md) for the
phased plan.

**Analytical layer moved:** `structure.py` (format pass) and `detect_tabs.py`
(vision tab detection) — the decision/contradiction/open-question extraction
and tab-aware grouping referenced throughout this doc — now live in the
private `cap-guide-analysis` package, not in this repo. `capt guide --ai`
imports them from there; the deterministic pipeline (ingest + render) needs
nothing beyond cap-tools.

## Current status

| Capability | Status |
|---|---|
| Ingest single-segment `.cap` → guide | ✅ validated on real recording |
| Ingest **multi-segment** `.cap` (global timeline) | ✅ 58 steps, 0 failures |
| Click → screenshot + CSS click-marker overlay | ✅ (cursor x/y normalized) |
| End-of-segment seek clamp | ✅ |
| **End-to-end on a real 18-min recording** (transcript → analyzed items → reviewed doc) | ✅ validated (see audit) |
| Narration → transcript | ✅ **wired to WSL server** (`transcribe.py`; faster-whisper/parakeet/HF, CUDA) — 18-min → 25s, word-level |
| Analyzed item-breakdown doc — **HTML + Markdown** | ✅ `build_walkthrough_doc.py` |
| Two-agent review (text accuracy + screenshot/tab match) | ✅ ran; fixes applied |
| Automated analysis via the format pass (not hand-authored) | ✅ `structure.py` (Ollama, `--tabs` + transcript-anchored) — 41 items, correct 4-tab grouping |
| Cursor-region rectangle overlay | ✅ built + validated (`build_walkthrough_doc.py --cursor`; 49/54 confident regions, dwell-cluster bbox) |
| Frame-based tab detection | ✅ **v2 done** (`detect_tabs.py --video`, `gemma4:31b-cloud`, tab-as-time-span) — found the Print tab, 4 clean spans |
| **Fully-automated doc** (no hand-authoring) | ✅ transcript → `structure.py --tabs` (anchored timestamps) → `build_walkthrough_doc` → HTML+MD, correct 4-tab grouping |
| MCP tools / add-on | ☐ planned |

**Latest run & retrospective:** see
[`doc-builder/docs/pipeline-audit-2026-06-14.md`](doc-builder/docs/pipeline-audit-2026-06-14.md)
— full backwards audit, current-state read, and prioritized next steps. The app
under review turned out to have **four** tabs (Studio/Build/Print/Review); the
review caught a missed Print tab and 4 wrong-tab frames, all fixed.

**Next step:** the full automated pipeline now works (transcript → tab-aware,
anchored, illustrated HTML+MD). Remaining: decide the 3 open questions (your
session), then **productize** — `cap-guide` CLI + MCP tools (`list_recordings`,
`ingest`, `get_steps`, `render_guide`) on `mcp_server.py`, optional folder watcher.

## Known limitations

- Generated `guide.html` inlines frames as base64 (e.g. ~37 MB for 58 steps).
  Productization will externalize frames to files.
- `cap_ingest.py` requires **Studio**-mode `.cap` recordings (Instant mode has
  no per-stream cursor data).
- Transcription/format-pass endpoints degrade gracefully when unavailable
  (guide is produced click-only, without narration).
