# Roadmap & Future Proposals

## Current state (2026-06-14) — validated prototype

The full pipeline works end-to-end with **no hand-authoring**:

```
Cap Studio .cap
  → transcribe.py            (WSL server, ?provider=faster-whisper|parakeet|hf, CUDA)
  → detect_tabs.py --video   (vision tab-as-time-span → tabs.json; gemma4:31b-cloud)
  → structure.py --tabs      (format pass → items.json; transcript-anchored, tab-bucketed)
  → build_walkthrough_doc.py (--cursor → index.html + index.md + named images, region overlays)
```

On the 18-min Microfactory recording this produced a correct 4-tab, illustrated,
HTML+MD breakdown automatically (41 items vs 54 hand-authored). See
[DECISIONS.md](DECISIONS.md) D1–D10 and
[pipeline-audit-2026-06-14.md](doc-builder/docs/pipeline-audit-2026-06-14.md).

All hard unknowns are resolved. What remains is productization + polish.

## Deferred (waiting on you)
- The **3 open questions** in the Microfactory doc — single-print vs iterations;
  Get-Second-Opinion button vs tab; outcome / manual-logging clarity. To be
  decided in a later session.

## Near-term — productize as a CLI + MCP "Cap add-on"
1. **`cap-guide` CLI** — one command wrapping the chain (`ingest <.cap> → guide`),
   flags for provider/model/output, with step caching (skip steps whose inputs
   are unchanged).
2. **MCP tools** on `mcp_server.py` — `list_recordings`, `ingest(path)`,
   `get_steps(path)` (structured JSON an agent can edit), `render_guide(path, format)`.
   Makes the whole thing agent-drivable; the `.cap` dir + `steps.json`/`items.json`
   are the contract.
3. **Folder watcher** (optional) on `%APPDATA%/so.cap.desktop/recordings` to
   auto-draft a guide per new Studio recording.
4. **Drive the `cap` CLI** (bundled at `~/.cap/bin`, verified) instead of manual
   Studio steps: `cap project validate` → process → optional `cap export -o out.mp4`
   (renders the **auto-zoomed video headlessly** — no Studio toggle/export). Cap also
   ships an agent skill (`skill/cap/SKILL.md`) — a natural fit for our MCP/agent flow.
5. **Auto-framed SOP screenshots from auto-zoom:** either (a) crop our own frames from
   `timeline.zoomSegments` + cursor focus (fast, no full render), or (b) pull frames
   from the `cap export` polished video. (a) is the lightweight default; (b) is most
   faithful to Cap's look + yields a shareable video artifact alongside the doc.

## Enhancement backlog (found during the spike)

**Accuracy / quality**
- **Frame-accurate tab boundaries** — currently ±sampling interval (~20s).
  Binary-search each transition, or sample only near tab-bar clicks (clicks in
  the tab-bar y-band from `cursor.json`) → fewer vision calls + precise edges.
- **Robust frame selection** — pick each item's screenshot from a frame on the
  correct tab (cross-check spans) and skip mid-transition/blurred frames.
- **Better item anchoring** — token-overlap works; embeddings + word-level
  alignment would tighten it.
- **Granularity** — auto pass got 41 vs 54 hand items; tune the prompt / chunk
  by tab to capture finer-grained items.
- **Cursor shape** (hand/ibeam/pointer) — use to refine region overlays and
  classify interactions (hover vs type).
- **Multi-segment `.cap`** — verify global vs per-segment time mapping across
  `detect_tabs` / `structure` (cap_ingest already handles multi-segment).
- **Transcription** — use larger models / domain vocabulary for harder audio
  (the WSL server already supports model selection + parakeet).

**Output / UX**
- **docx / pdf export** (pandoc) from the canonical HTML.
- **TOC / per-tab nav** and "decided vs open" status chips in the HTML.
- **Region polish** — multiple regions per item, dwell-heatmap, confidence shading.
- **Single-file export** option (inline base64) alongside the file-based dir.

**Engineering**
- Frame extraction **batching** (one ffmpeg pass) for long recordings.
- **Caching / resume** across pipeline steps.
- **Config consolidation** (offsets, models, endpoints in one place).
- **Tests** + a small fixture `.cap` for regression.

## Review / quality loop
- Make the **two-agent review** (text accuracy + screenshot/tab match) a standard
  pipeline stage that auto-applies low-risk fixes (timestamp nudges, tab
  reassignment) and surfaces the rest.

## Longer-term vision
- **Technical sidecar** (from the original product concept) — for browser
  workflows, a Playwright/UI-Automation layer capturing selectors + network
  alongside the guide → a "Technical Reference" view next to the user guide.
- **Agent harness pairing** — agent ingests a `.cap`, reasons over structured
  items, edits captions/decisions, and re-renders. The format is the interface.
- **Build-on-Cap** — revisit contributing to / forking Cap once its recording
  fidelity and agent mature; today we *consume* Studio recordings (cleanest).
- **Real-time / live mode** — out of scope now; the value here is post-hoc analysis.

## Backend / packaging (product phase) — see DECISIONS D2/D3
- Keep **one OpenAI-compatible URL** as the client contract (WSL server for
  transcription + chat; Ollama for vision / the format pass).
- If bundled into a desktop app: **native sidecars** (Ollama + CTranslate2 /
  whisper.cpp), never a PyInstaller-frozen torch monolith.
