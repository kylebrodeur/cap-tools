# Decision Log

Why the architecture is what it is. Newest decisions first. This captures the
reasoning that would otherwise be lost between sessions.

---

## D10 — Frame-aware tab detection + transcript anchoring → fully automated (2026-06-14)

**Result:** The pipeline now produces a correctly-structured, tab-aware,
illustrated doc end-to-end with **no hand-authoring.**

- **Tab detection (v2, `detect_tabs.py --video`):** tab-as-time-span. Sample
  frames, crop the tab-bar strip, ask a vision model "which tab / None if no bar
  visible", collapse to spans. Engine = **`gemma4:31b-cloud`** (local vision
  `minicpm-v4.6` tested too weak: 1/3; `gemma4:12b` ok on crops; the 31b-cloud
  is reliable). On Microfactory: 4 clean spans (Studio 0–7:00, Build 7–11:00,
  Print 11–16:20, Review 16:20–end) — **found the Print tab** the narration
  never named.
- **Transcript anchoring (`structure.py`):** the format-pass model fabricates
  drifting timestamps (items ran to 29:00 on an 18:22 clip), so we **ground each
  item's `t` by matching its text back to the transcript segment** (token
  overlap), then `regroup_by_tabs` buckets items into the detected spans. After
  anchoring, every item's `t` lands inside its tab span (max 1061s ≤ 1102s).
- **Output:** auto doc = 41 items / correct 4 tabs (vs 54 hand-authored);
  `walkthrough-auto/`. Renderer hardened against missing `decision`/`said`.

## D9 — Cursor-region rectangle overlay (BUILT + validated, 2026-06-14)

**Decision / result:** Added a confidence-gated **cursor-region rectangle
overlay** to the generated doc (`build_walkthrough_doc.py --cursor cursor.json`).
On the Microfactory recording: **49/54 items got a region**; visually validated
(e.g. studio-06 boxes the Environment Simulator block; studio-10 boxes the
Quick-Load Benchy / Generate Primitive cluster). Algorithm: dwell-weighted
cursor `moves` in a [t-5s, t+2s] window → trimmed (10–90 pct) bounding box →
gate out if the box exceeds ~45% of the screen. Rendered as a CSS-% dashed box.

**Why:** Most feedback items are narrated *without* clicking — the user gestures
with the cursor ("this section here"). Cursor dwell during the narration window
is the strongest "what am I pointing at" signal. Plan: dwell-weight cursor
`moves` in the item's window, cluster, bbox the dominant cluster, draw a
rectangle; gate on tightness (< ~45% of screen) with a dot fallback. Treat as
experimental and validate visually. Cap's cursor *shape* (hand/ibeam/pointer) is
a future refinement. See `doc-builder/docs/pipeline-audit-2026-06-14.md`.

## D8 — End-to-end validated; local transcription stand-in; app has 4 tabs (2026-06-14)

**Decision / result:** The full pipeline (Cap `.cap` → transcript → clicks +
frames → analyzed item breakdown → two-agent review → HTML + Markdown) is
**validated on a real 18-minute narrated recording.** The spike's core question
is answered yes.

**Notes:**
- **Transcription stand-in:** `transcribe_local.py` (faster-whisper `small.en`,
  CPU int8) is used until the WSL endpoint is wired. Quality was good; swap-in
  later behind the same transcript schema.
- **Analysis is still hand-authored** (`items.json`); D-next is to make it the
  automated format pass for reproducibility.
- **Review caught real defects:** the app has **four** tabs
  (Studio/Build/Print/Review) — narration never named "Print", so tab structure
  must be derived from frames, not narration. 4 wrong-tab frames were re-timed.
- **Output is HTML + Markdown** (`build_walkthrough_doc.py`), images as named
  files in a dir — consistent with D1 (HTML-first; export from it).
- Full retrospective: `doc-builder/docs/pipeline-audit-2026-06-14.md`.

## D7 — Productize as a CLI + MCP "Cap add-on" (2026-06-14)

**Decision:** Ship as a CLI core + MCP tool layer, optionally watching Cap's
recordings folder — not a GUI app.

**Why:** The whole thing is a pure transform (`.cap` directory → guide) with no
UI surface of its own. Cap owns capture; we own the intelligence. A CLI is the
core; MCP tools (`list_recordings`, `ingest`, `get_steps`, `render_guide`) make
it agent-drivable — an agent reasons over structured steps, not pixels. The
existing `mcp_server.py` is the place to add them.

---

## D6 — Consume Cap recordings; don't build our own recorder (2026-06-14)

**Decision:** The product input is a **Cap Studio `.cap` directory**. We are a
post-processor over it. Our standalone `record.py` becomes a fallback only.

**Why:** Reading Cap's source (CapSoftware/Cap) showed a `.cap` Studio recording
already contains everything we need, in documented JSON, at high quality:
high-q `display.mp4`, a **separate clean mic track**, `cursor.json` (clicks +
move trail, x/y normalized 0..1), optional word-level `captions.json`,
keyboard events, and screenshots. Richer than our hand-rolled gdigrab + pynput +
Whisper combo, cross-platform, and zero capture code to maintain. Validated:
`cap_ingest.py` produces guides from the user's real single- and multi-segment
recordings.

**Caveats found:** Cap has **two modes** — *Instant* (single muxed
`output.mp4`, fast-share, lower quality) vs *Studio* (multi-stream, high
quality, has cursor data). Use Studio. Cap does **not** write `captions.json`
locally (its transcription is cloud-only), so transcription is always ours.
Format fully documented in `spike/SPIKE_IMPROVEMENT_BRIEF.md` §7.1.

---

## D5 — Decouple capture streams (2026-06-14)

**Decision:** Treat screenshots, narration, and video as independent streams so
guide quality never depends on a single video encoder.

**Why:** Guide value = crisp per-step screenshots. Pulling frames from a
compressed video caps quality. Better: screenshots from high-res stills /
high-q display stream, narration from a clean isolated mic track, full-screen
video optional. Cap's Studio format already separates these (separate mic
track, per-segment display, cursor data) — which is what made D6 attractive.

---

## D4 — "Chat" was the wrong frame; it's a single format pass (2026-06-14)

**Decision:** The AI step is **not** a chatbot. It's one invisible
"format pass": a single OpenAI-compatible call with a fixed system prompt that
turns the raw transcript into clean bullets. No multi-turn.

**Why:** This is how dictation tools actually work — superwhisper bundles it as
a "mode" (model + one post-processor + prompt), Wispr Flow calls it "Smart
Formatting." Much of the cleanup (filler words, punctuation) is rule-based; the
model only does structure. Consequence: the **same WSL service** that does
transcription can do the format pass — **no separate Ollama instance needed.**

---

## D3 — Backend packaging: native sidecars, not a frozen monolith (2026-06-14)

**Decision (product phase only):** If/when bundled into a desktop app, ship
native sidecars — Ollama (or the WSL tool) for the format pass, a CTranslate2 /
faster-whisper native binary for ASR — not a PyInstaller-frozen torch monolith.

**Why:** Freezing torch + CUDA via PyInstaller yields a 2.6 GB+, fragile bundle.
CTranslate2/whisper.cpp have native CUDA binaries; Ollama is a single binary and
the standard desktop-AI sidecar. The client only ever sees one OpenAI-compatible
URL, so the runtime behind it can change without touching the client. **Not in
scope for the spike** — the spike uses localhost HTTP.

---

## D2 — One backend serves transcription + format pass (2026-06-14)

**Decision:** The WSL transcription tool is the single inference backend; it
serves an OpenAI-compatible endpoint used for both transcription and the format
pass (BYOK-configurable to point elsewhere). One service to run, not two.

**Why:** "Don't reinvent / don't manage separate instances." The tool already
has CUDA + multiple engines + OpenAI-compatible support. Only transcript text
leaves the box — never video or frames.

---

## D1 — Pivot to "Wispr Flow for video"; HTML-first output (2026-06)

**Decision:** Reframe from a step-guide generator toward instant, low-friction
**bulleted summaries + clean screenshots** pasteable into AI or saved as files.
**HTML is the source of truth**; Markdown/docx are generated from it.

**Why:** The differentiator across dictation/recording tools is post-processing
quality and friction, not raw transcription. HTML-first keeps one canonical,
styleable artifact and a clean export path.

---

### Superseded / earlier thinking

`ARCHITECTURE.md` predates the Cap decision (D6). It assumes ffmpeg frame
extraction as the primary path, a screenpipe-style native capture layer, a
Tauri GUI shell, and UACS for context. Those ideas remain useful references, but
where they conflict with the decisions above, **the decisions above win.**
