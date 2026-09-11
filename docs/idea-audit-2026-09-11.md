# Idea audit — cap-tools docs vs Cap's native CLI (2026-09-11)

Companion to the scout inventory (`agent://DocIdeaScout`, full per-doc detail in
session transcript). One page: what got better, what Cap superseded, what to
rethink, and what only cap-tools fills.

## What got better since the docs were written

- **`cap export-preview`** — the frame-extraction fragility that motivated
  vendoring PyAV is gone for `cap` users; `capt guide` already prefers it
  (integrated 2026-07-31). The remaining ask on CapSoftware/Cap#2059 is a
  batch `--frames-at` file-output mode.
- **Cap's agent surface** (`cap guide --json` manifest, `cap mcp serve`,
  `cap agents install`, copy-paste setup prompt at cap.so/docs/agents) —
  validates the "agents are a first consumer" bet behind `capt`.
- **v0.6.0 (2026-09-03)** — desktop edit/export speedups; `cap update`
  available on this machine (0.5.9 installed).

## Superseded — stop building/keeping these

| Idea (source doc) | Native replacement |
|---|---|
| Thin record lifecycle wrappers (`FINDINGS`, `refactor-plan` `cap_api.py`) | `cap record start/stop --detach`, `recordings`, `caps status/wait` |
| Target discovery + readiness wrappers (`INVENTORY`, UC-4) | `cap targets`, `cap doctor`, `cap selftest` |
| Screenshot utility (`INVENTORY` item 15, UC-7) | `cap screenshot` |
| Upload/share wrapper (UC-10) | `cap upload`, `caps` family |
| Generic MCP/skill bootstrap (`decisions` D7, productization) | `cap mcp serve`, `cap agents install` |
| Manual Studio polish walkthrough (`FINDINGS` §§1–6) | headless config-driven export |
| Standalone gdigrab recorder (`decisions` D6 — already archived) | Cap Studio |
| Issue-first upstream route (`upstream-agent-brief`) | Richie approved a direct PR; scope still open |
| WSLg browser bridge (`INVENTORY`) | self-rejected; Windows-native browser is the reliable path |

## Rethink — ideas that need re-scoping, not dropping

- **Preflight** — Cap-side gates (doctor/targets) are native; `capt preflight`
  stays valuable only as *cross-tool* glue (Playwright presence, URL
  reachability, output dir, Input Monitoring, G8 doctor gate — added today).
  Don't grow Cap-duplicating gates.
- **D7 "guide MCP + watcher"** — generic MCP plumbing is native now; scope to
  guide-specific tools only (`ingest`, `get_steps`, `render`, item editing).
- **Transcription** — `cap caps transcript` can replace acquisition plumbing;
  keep local ASR only when privacy/domain-tuning demands it (D2–D4 still
  stand for the private analytical layer).
- **`cap doc` upstream PR** — rename settled (`doc`, not `guide`); open
  question is whether the PR ships deterministic guide only, or includes
  agent-workflow extras (record/beat techniques). Prototype is validated;
  Rust port is the remaining work.
- **Assembly (`assemble.py`)** — still a real gap (UC-6), but consider whether
  Cap's own multi-segment export covers the common case before investing in
  the ffmpeg manifest pipeline.

## Still gaps only cap-tools fills (the durable core)

1. **Real-click GlobalCapture** — CGEventTap click/keystroke tracking +
   Cmd+Shift+M marks (macOS); Cap has no equivalent.
2. **Scripted step replay** — declarative `goto/click/fill/wait/mark` with
   semantic event timing; Cap records but doesn't drive the app.
3. **Event → zoomSegments construction/merge** — semantic windows, overlap
   merge, config merge (today: + events sidecar JSONL).
4. **Authenticated scripted recording** — storageState/persistent profile
   (added today) for logged-in apps (ReelBinder).
5. **Recording → illustrated guide** (`capt guide`) — steps from clicks+zoom,
   `export-preview` frames, cursor-region overlays (D9), tab-aware grouping
   (D10).
6. **Analytical layer** (`cap-guide-analysis`) — decisions/contradictions/
   open-questions from narrated walkthroughs; privacy-first, BYO endpoint.
7. **Beat orchestration/assembly** — per-beat reruns, rehearsals, multi-clip
   assembly with VO/captions (UC-2/6/13).

## Agent skills layer on top (per direction, 2026-09-11)

Cap ships its own skill/MCP for the *Cap surface*; ours should layer, not
compete:

- `cap-cli` skill → keep as the WSL bridge only (narrow, complementary —
  already scoped correctly in its SKILL.md).
- New `capt` skill (agentskills.io) teaching: demo/record/pick, events
  sidecar, storage-state auth, guide + `--ai` handoff, ReelBinder window
  recipe. Installable via the existing `bin/install-skill.js` npx flow.
- Positioning: Cap's skill answers "how do I drive Cap"; ours answers "how do
  I *produce a demo/guide* with Cap as the renderer."