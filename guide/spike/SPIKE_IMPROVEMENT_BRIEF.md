# Spike Improvement Brief — for a local coding agent (or agent team)

> **STATUS (2026-06-14): largely SUPERSEDED — most of this is now built.** The
> pipeline consumes Cap Studio recordings end-to-end: `transcribe.py` (WSL
> server) → `detect_tabs.py --video` (tab spans) → `structure.py --tabs` (format
> pass, transcript-anchored) → `build_walkthrough_doc.py --cursor` (illustrated
> HTML + Markdown with cursor-region overlays). For current state see
> [../README.md](../README.md), [../DECISIONS.md](../DECISIONS.md) (D1–D10), and
> [../ROADMAP.md](../ROADMAP.md). This brief is still the authoritative
> reference for the **Cap `.cap` format (§7.1)**; note the product path
> *consumes* Cap rather than building the standalone recorder this brief opens
> with.

> **Read this whole file before touching code.** You have no memory of the
> conversation that produced it; everything you need is here. When in doubt,
> prefer the smallest change that satisfies the acceptance criteria and keep
> the recording path working on native Windows.

---

## 1. What this project is

A **spike** validating a data pipeline for an automated "record-a-workflow →
get-a-guide" tool. The owner is pivoting it toward a **Whispr-Flow-for-video**
experience: record screen + narration, then produce **bulleted summaries of
what was discussed plus clean screenshots**, in output that can be **pasted
into AI models or saved as various files**.

The spike answers one question: *does the combined data (screen recording +
click timestamps + transcript) produce a useful draft guide with reasonable
frames at reasonable moments?* See `docs/guide-tool-spike-plan.html` (one
level up, under `doc-builder/docs/`) for the original plan and Go/No-Go gate.

### File map

```
guide-tool/
  spike/
    record.py            # Windows-only: gdigrab screen + dshow mic + pynput clicks
    extract_frames.py    # ffmpeg frame pull at click+0.5s
    transcribe.py        # HTTP client → transcription server (currently stubbed)
    assemble.py          # joins events + transcript + frames → guide.html
    spike-output/        # runtime artifacts (recording/, transcript/, frames/, output/)
    SPIKE_IMPROVEMENT_BRIEF.md   # <- you are here
  guide.py               # project-management CLI (sessions, scaffolding)
  pyproject.toml         # uv-managed; deps: rich, mcp, pynput, jinja2
```

### Runtime environment (critical)

- **OS:** Windows 11. Package manager: **uv** (already installed). ffmpeg is on
  PATH via Scoop. `python` is 3.14 via uv's venv. Run scripts with
  `uv run spike/<script>.py` from the `guide-tool/` directory.
- **Windows/WSL split — do not break this:**
  - `record.py` and `extract_frames.py` **must run on Windows** (gdigrab,
    dshow microphone capture, Windows ffmpeg). Do **not** make them depend on
    WSL.
  - `transcribe.py` and the AI-structuring step talk to servers over
    **localhost HTTP**. The transcription server lives in **WSL2**; the
    structuring model is **local Ollama** (or a configured OpenAI-compatible
    endpoint). HTTP over localhost crosses the WSL/Windows boundary cleanly.
- **Hardware:** RTX 5080 — local GPU inference (Ollama / CUDA) is expected and
  preferred over cloud.

### Locked design decisions (do not relitigate)

1. **Output is HTML-first.** The self-contained HTML guide
   (`spike-output/output/guide.html`, base64-embedded images) is the
   source of truth. Markdown / docx / pdf are **generated from it** on demand,
   not maintained separately.
2. **Structuring is a single invisible "format pass," NOT chat.** This is how
   dictation tools actually work (superwhisper "modes", Wispr "Smart
   Formatting"): one fixed system prompt transforms the raw transcript into
   clean bulleted notes in a single shot — no conversation, no multi-turn.
   Call it over an **OpenAI-compatible** endpoint, which the **WSL transcription
   tool already serves** — so the *same* WSL service does transcription **and**
   the format pass; **no separate Ollama needed.** Keep it configurable
   (base_url + optional BYOK key) via the `openai` package. **Only transcript
   text** leaves the box — never video/frames. Cheap cleanup (filler words,
   punctuation, capitalization) should be rule-based; the model only does
   structure/bullets.
3. **Privacy:** nothing leaves the machine except transcript text to the
   user-configured structuring endpoint (which defaults to localhost).

---

## 2. Audit findings you are fixing

Severity tags: 🔴 correctness (spike validity) · 🟡 quality · 🟢 ease-of-run ·
🔵 pivot-readiness.

| # | Sev | File | Problem |
|---|-----|------|---------|
| 1 | 🔴 | `record.py` | **Click/video timeline drift.** `start_time` is set right before `Popen(ffmpeg)`, but ffmpeg's frame `t=0` is hundreds of ms–~1.5s later (dshow audio init is slow). Clicks are systematically *early* vs video, so "click+0.5s" can precede the UI response. |
| 2 | 🔴 | `record.py` / `assemble.py` | **No click debouncing.** Every pynput press becomes a step; double-clicks/drags create duplicate near-identical frames. Matches the plan's own No-Go condition. |
| 3 | 🔴 | `extract_frames.py` | **Seek accuracy not guaranteed.** `-ss` before `-i` is fast input seek; with long GOPs the frame may be off. |
| 4 | 🟡 | `transcribe.py` / `assemble.py` | **Word-level timestamps unused.** The owner's own `transcript-format-recommendations.md` calls this the single biggest screenshot-quality win. |
| 5 | 🟡 | `assemble.py` | **Naive transcript join.** `nearest_segment()` matches closest `start` only; can pick the wrong segment. |
| 6 | 🟢 | all | **Four manual copy-paste steps.** Owner wants it "easier to run even for the spike." |
| 7 | 🟢 | repo | No `.gitignore` for `spike-output/`; no first-run check that ffmpeg/uv deps are present. |
| 8 | 🔵 | `record.py` / `assemble.py` | **Multi-monitor click mapping.** `events.json` stores *global* x/y but frames are cropped to one monitor; click-marker overlays need `x−screen.x, y−screen.y`. The screen offset is currently lost. |

---

## 3. Work breakdown — phases → steps → tasks

Phases are ordered by dependency. **Phase A first** — it makes the spike's
result trustworthy; without it, good or bad output could be a timing artifact.
Phases D/E are the pivot. An agent team can parallelize within a phase but
should respect cross-phase ordering (A → B → C → D → E; F can go any time).

### Phase A — Pipeline correctness 🔴 (do first)

**Step A1 — Eliminate timeline drift (`record.py`)**
- Task: Don't trust wall-clock at `Popen`. Start the click clock only once
  ffmpeg is actually capturing. Implement one of:
  - Parse ffmpeg stderr for the first `frame=` line (or use `-progress pipe:`)
    and set `start_time` at that moment; **or**
  - Capture `start_time = time.time()` at the first decoded frame by adding a
    1-frame "sync" detection, **or**
  - At minimum, measure the offset once and store it in `events.json` as
    `capture_offset_s` so downstream can subtract it.
- Acceptance: a click made exactly when a known on-screen event happens lands
  within ±1 video frame of that event in the extracted frame. Document the
  method in a code comment.

**Step A2 — Debounce clicks (`record.py`)**
- Task: In `on_click`, ignore a press if it's within `DEBOUNCE_MS` (default
  400) **and** `DEBOUNCE_PX` (default 5) of the previous *recorded* press.
  Keep recording `button`; add a config flag `LEFT_CLICK_ONLY` (default True
  for the spike). Make thresholds constants at the top.
- Acceptance: a manual double-click produces exactly one event; a slow drag
  produces one event.

**Step A3 — Guarantee seek accuracy (`extract_frames.py` + `record.py`)**
- Task: Add `-g {FRAMERATE}` (keyframe every ~1s) to the libx264 encode in
  `record.py`. In `extract_frames.py`, keep fast input seek but verify; if you
  observe drift, switch to `-i` then `-ss` (accurate, slower). Make the offset
  (currently `OFFSET = 0.5`) a shared constant sourced from one place.
- Acceptance: extracted frame timestamp matches `click_t + OFFSET` within one
  frame.

### Phase B — Ease-of-run 🟢

**Step B1 — One-command orchestrator**
- Task: Add `spike/run.py` (and/or a `guide.py spike` subcommand) that runs
  record → extract → transcribe → assemble in sequence, with `--skip-record`
  to re-run downstream steps on an existing recording. Pass through
  `--screen/--mic/--no-audio` to `record.py`.
- Acceptance: `uv run spike/run.py` produces `guide.html` end-to-end given a
  running transcription server.

**Step B2 — Guardrails & hygiene**
- Tasks: add `spike-output/` (and `*.mp4`) to a `.gitignore`; on startup check
  ffmpeg is on PATH and required Python deps import, with a clear error if not;
  centralize all paths/constants (`SPIKE_ROOT`, `OFFSET`, framerate, debounce)
  in one small `spike/config.py` imported by the others.

### Phase C — Transcription wiring 🟡

**Step C1 — Make `transcribe.py` config-driven**
- Task: Replace the guessed port/path with a config block + env overrides
  (`TRANSCRIBE_URL`, etc.). Keep the existing dual-format handling
  (`whisper_result.segments` **and** flat `segments`). Request **word-level
  timestamps** if the server supports a flag; pass video duration through if
  available. **The real endpoint URL/response shape is still TBD from the
  owner — leave it clearly configurable and documented at the top of the
  file.**
- Acceptance: pointing `TRANSCRIBE_URL` at a compatible server yields
  `spike-output/transcript/transcript.json` with `segments[]` and, when
  available, per-segment `words[]`.

**Step C2 — Use word timestamps in `assemble.py`**
- Task: Improve `nearest_segment()` → prefer the segment that *contains* the
  click time; when `words[]` exist, select frame text around the spoken word
  nearest the click. Keep a graceful fallback to segment-level.

### Phase D — Format pass (the pivot — a "mode," not chat) 🔵

**Step D1 — Single-pass transcript formatter**
- Task: Add `spike/structure.py`. ONE function: raw transcript → structured
  output via a **single** OpenAI-compatible call with a fixed system prompt
  (the "guide mode"). No multi-turn/chat loop. Use the `openai` package
  (`uv add openai`). Config: `STRUCTURE_BASE_URL` (default = the WSL tool's
  OpenAI-compatible URL, NOT a separate Ollama), `STRUCTURE_API_KEY` (optional
  BYOK), `STRUCTURE_MODEL`. Send **only transcript text**. Do filler/punctuation
  cleanup with rules first; the model only does structure/bullets.
- Acceptance: given `transcript.json`, returns a short title, an overall
  **bulleted summary of what was discussed**, and per-step one-line captions
  keyed to click indices/timestamps. Works against the WSL service with no
  separate model server running.

**Step D2 — Feed structuring into the HTML guide**
- Task: `assemble.py` consumes the structured output: render the bulleted
  summary at the top and use AI captions for each step card (fallback to
  nearest-transcript text if structuring is unavailable). HTML stays the
  source of truth.
- Acceptance: `guide.html` opens with a clean bulleted summary + screenshot
  cards; works with structuring disabled (graceful degrade).

### Phase E — Export layer 🔵

**Step E1 — HTML → other formats**
- Task: Add `spike/export.py` that converts `guide.html` to Markdown and docx
  (and optionally pdf). Prefer `pandoc` if present; otherwise a Python
  fallback (`markdownify`/`html2text` for md, `python-docx` or pandoc for
  docx). Markdown export should be **paste-into-AI clean** (bullets + image
  refs; decide inline-base64 vs. an adjacent `images/` folder).
- Note: `docling` / `any2md` were raised by the owner. Their better fit is
  **ingesting existing `.docx` SOPs as style/structure references**
  (see `../*.docx` in the SOPs folder) rather than HTML→md export. Evaluate
  but don't force them into the export path if pandoc is cleaner.
- Acceptance: `uv run spike/export.py --to md,docx` emits the files from the
  current `guide.html`.

### Phase F — Pivot-readiness 🔵 (independent)

**Step F1 — Preserve click coordinates relative to the captured screen**
- Task: In `record.py`, store the selected screen's offset/size in
  `events.json` (e.g. `{"screen": {"x":..,"y":..,"w":..,"h":..}, "events":[...]}`
  — keep backward-compat or migrate `assemble.py` to the new shape). This lets
  later work draw a "click here" marker at `x−screen.x, y−screen.y` on the
  cropped frame.
- Acceptance: `events.json` records enough to map any global click into
  captured-frame pixel space.

---

## 4. Global constraints & definition of done

- **Don't break Windows recording.** `record.py`/`extract_frames.py` stay
  native-Windows. Test `uv run spike/record.py --list-sources` still works.
- **Config over hardcoding.** New tunables go in `spike/config.py` or env vars,
  documented at the top of the relevant file.
- **Graceful degradation.** Each new dependency (transcription server,
  structuring model, pandoc) being unavailable should produce a clear message
  and, where possible, a reduced-but-working output — not a stack trace.
- **No secrets in code.** API keys come from env only.
- **Keep it uv-native.** Add deps with `uv add <pkg>`; run with `uv run`.
- **Per-phase verification.** After each phase, do a real run (or a dry run
  with the existing sample assets in the SOPs folder:
  `ai-accelerator-manual-badge-certificate-delivery.mp4` +
  `..._20260311_123457.json`) and report what you observed against the Go/No-Go
  gate in the spike plan.

## 5. Suggested agent-team split

- **Agent 1 (Capture):** Phase A + F — owns `record.py`, `extract_frames.py`.
- **Agent 2 (Plumbing):** Phase B + C — orchestrator, config, transcription.
- **Agent 3 (Intelligence):** Phase D — structuring client + assemble wiring.
- **Agent 4 (Output):** Phase E — export, format fidelity.
- A → (B, F) → C → D → E. Agents 1–2 can start in parallel; 3 waits on C; 4
  waits on D.

---

## 6. Backend packaging — PRODUCT PHASE ONLY, do **not** solve during the spike

The spike must keep the **localhost HTTP boundary**: the WSL transcription tool
(serving both `/v1/audio/transcriptions` and `/v1/chat/completions`) is hit
over HTTP. No bundling, no sidecar, no freezing. Do not let packaging block
validating frame/summary quality.

**The client contract is fixed:** every consumer (`transcribe.py`,
`structure.py`) talks to a single **OpenAI-compatible base URL**. How that URL
is *served* can change later without touching the client.

When the product (Tauri) phase arrives, the decided direction is **native
sidecars, not a frozen Python monolith**:

- **Structuring (chat):** bundle **Ollama** as a Tauri sidecar (`externalBin`).
  Single native binary, OpenAI-compatible, manages its own models. This is the
  standard desktop-AI sidecar pattern.
- **Transcription (ASR):** a **CTranslate2 / faster-whisper** native Windows
  binary (CUDA via cuBLAS+cuDNN alongside), or whisper.cpp's native CUDA build.
  **Avoid PyInstaller-freezing torch+CUDA** — that yields a 2.6 GB+ fragile
  bundle and is explicitly rejected.

The Tauri app spawns/stops both sidecars so the user manages zero instances.
Open question for that phase: confirm the WSL tool's ASR backend (faster-
whisper/CTranslate2/whisper.cpp = easy native repackage; openai-whisper/torch =
swap to CTranslate2 for shipping). None of this is in scope for the spike.

---

## 7. Recorder & capture strategy — decouple the streams (product direction)

**Decision (updated after reading Cap's source).** The earlier "low quality"
worry was **Cap's Instant mode** (single muxed `content/output.mp4`, tuned for
instant-share). Cap's **Studio mode** is the high-fidelity, multi-stream,
editable format — quality is a *mode choice*, not a Cap limit. So the
recommended product input is **a Cap Studio recording**: consume the `.cap`
project directory and make our tool a **pure post-processor** with no capture
code. Cap Studio already records clicks, cursor moves, a clean isolated mic
track, optional word-level captions, keyboard events, and screenshots — richer
than the spike's own capture. Fall back to our own capture only if Cap can't be
a dependency. If Cap's (young) transcription isn't reliable locally, ignore
`captions.json` and feed Cap's separate `mic` track to the WSL transcription
tool. See §7.1 for the format.

**The architecture this implies — capture three streams independently, so
guide quality never depends on a video encoder (ours or Cap's):**

1. **Screenshots = independent full-resolution stills** grabbed at click time
   (direct GDI/DXGI / `mss` PNG capture at click+offset), **not** frames
   re-derived from compressed video. This is how Scribe/Tango do step guides
   and yields pixel-perfect images regardless of any recorder's quality.
2. **Narration = clean mic audio only** → transcript → format pass → bullets.
   The summary needs the *audio*, not full-screen video.
3. **Full-screen video = optional.** Only for a shareable playable clip; if
   wanted later, let Cap own it. The guide does not depend on it.

**Spike vs product:** the spike may keep extracting frames from the recorded
video (it only needs to validate the concept). The **product** should capture
independent stills + audio. A worthwhile spike enhancement (optional): add a
high-res still grab at click+offset alongside the video frame, and compare
which produces better screenshots — that directly de-risks the product path.

### 7.1 Cap Studio `.cap` format (verified by reading CapSoftware/Cap source)

Root: `recording-meta.json` (`RecordingMeta`). `inner` is **Instant** (fast,
single `content/output.mp4`) or **Studio** (high-q, multi-stream). Use Studio.
A Studio project (single- or multi-segment) contains:

- `content/display.mp4` (or `content/segments/segment-N/display.mp4`) —
  `VideoMeta { path, fps, start_time, device_id }`. High quality.
- `mic` audio (e.g. `audio-input.mp3`) **separate** from `system_audio` —
  `AudioMeta { path, start_time, ... }`. Clean narration for transcription.
- `cursor.json` — `CursorEvents`:
  - `clicks[]`: `{ time_ms: f64, down: bool, cursor_num: u8 (button),
    active_modifiers: [str], cursor_id: str }`
  - `moves[]`: `{ time_ms: f64, x: f64, y: f64, ... }` — **x/y normalized 0..1
    to the (cropped) display** → multiply by display size for pixels.
  - cursor images map (shape per `cursor_id`).
- `captions.json` — `CaptionsData { segments: [ { id, start, end, text,
  words: [ { text, start, end } ] } ] }`. **Word-level** timestamps (seconds).
- `keyboard.json` — keystrokes + modifiers, timestamped.
- `screenshots/` — stills Cap already captures.

Implications for our pipeline (consume, don't capture):
1. **Clicks** come from `cursor.json.clicks` (filter to `down==true`, dedupe) —
   replaces pynput. Map normalized x/y → pixels for click markers.
2. **Transcript** comes from `captions.json` (already word-level) — or
   transcribe the `mic` track with the WSL tool if captions are absent.
3. **Screenshots**: extract `display.mp4` at `click.time_ms/1000 + OFFSET`, or
   use `screenshots/`. `start_time` fields let us align click/video/audio
   timelines precisely (no more startup-drift guesswork — see §3 Step A1).
4. **Agent harness:** the `.cap` dir is the serializable contract; expose
   "ingest `.cap` → guide" via `mcp_server.py` and hand the agent the
   structured `clicks`/`captions` to reason over.

(Reference clone left at `%TEMP%\cap-src` this session for follow-up reading.)
