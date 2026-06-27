# Agent Brief — Tighten `cap guide` and prepare it for upstream contribution to Cap

> **For a local coding agent.** You have no memory of the conversation that
> produced this — everything you need is here or in the linked files. Work on a
> branch. **Do NOT open a GitHub PR or post anything to GitHub** in this task —
> only prepare drafts. A human will submit the issue/discussion (and later the PR).

## 0. Read first (in this order)
1. [`CAP-UPSTREAM-PROPOSAL.md`](CAP-UPSTREAM-PROPOSAL.md) — the spec: a `cap guide`
   CLI subcommand + `crates/guide` for Cap. **This is what you are tightening toward.**
2. [`README.md`](README.md), [`DECISIONS.md`](DECISIONS.md) (D1–D10),
   [`ROADMAP.md`](ROADMAP.md), [`PRODUCTIZATION.md`](PRODUCTIZATION.md) — context.
3. [`spike/SPIKE_IMPROVEMENT_BRIEF.md`](spike/SPIKE_IMPROVEMENT_BRIEF.md) **§7.1** —
   the authoritative Cap `.cap` on-disk format reference.

## 1. Goal
Turn the working-but-sprawling spike into a **tight, documented reference
implementation of `cap guide`** that mirrors the proposed upstream CLI, and
prepare the **upstream materials** (issue + discussion + PR plan + a demo) so a
human can submit them. The Python reference impl is what the eventual Rust
`cap-guide` crate will be ported from — keep it faithful to that target.

## 2. What exists (environment + prototype)
- **Repo:** this directory (`guide-tool`), git on `main`. Toolchain: **uv** (Windows);
  `ffmpeg` on PATH; **Ollama** (`gemma4:12b` text, `gemma4:31b-cloud` / vision);
  a WSL transcription server at `http://localhost:8000` (`/transcribe?provider=…`).
- **Cap CLI** installed at `~/.cap/bin/cap.cmd` (`cap 0.1.0`): `cap export`,
  `cap record`, `cap project validate`, `cap screenshot`, `cap guide --json`
  (capability manifest). Cap is **AGPLv3** (core); repo `CapSoftware/Cap`.
- **Prototype scripts** in `spike/` (validated end-to-end on a real 18-min recording):
  | script | role | maps to upstream |
  |---|---|---|
  | `cap_ingest.py` | clicks → steps + frames + `steps.json` from a `.cap` | step derivation + frame extraction |
  | `build_walkthrough_doc.py` | items → `index.html` + `index.md` + named images; `--cursor` region overlays; dwell-cluster bbox | renderer + auto-framing |
  | `detect_tabs.py` | vision tab detection; `--video` = tab-as-time-span → `tabs.json` | (companion layer — app-specific) |
  | `structure.py` | transcript (+`--tabs`) → analyzed `items.json` via OpenAI-compatible LLM; transcript anchoring | optional `--ai` step-text (core) + deep analysis (companion) |
  | `transcribe.py` | transcribe a `.cap` audio track via the WSL server | caption source |
- **`.cap` format** (see §7.1): `recording-meta.json`; `content/segments/segment-N/`
  with `display.mp4`, `cursor.json` (`clicks[]` {time_ms,down,cursor_num}, `moves[]`
  {time_ms,x,y normalized 0..1}), `audio-input.ogg`, `keyboard.bin`;
  `content/cursors/`; `project-config.json` with **`timeline.zoomSegments`**
  (`{start,end,amount,mode:"auto"}`, no position → zoom follows the cursor),
  `captions`, `annotations`, `maskSegments` (redaction). Optional `captions.json`.

## 3. Tasks

### A. Consolidate into a tight `cap guide` reference implementation
Create a clean, single-entry module/CLI (e.g. `capguide/` package or
`spike/capguide.py`) that **reads a `.cap` directory directly** and mirrors the
RFC surface:
```
capguide <project.cap> [--out <dir>] [--format html|md|both] [--ai <openai-url> [--ai-model m]] [--json]
```
- **Deterministic core (must work with zero AI, fully local):**
  - Steps = union of `zoomSegments` (`mode:auto`) and click-down events, deduped/
    debounced, time-ordered. Each step's focal region = dwell-weighted cursor
    position in its window; crop size from the zoom `amount` (auto-framed screenshot).
  - Captions from `captions.json` if present; else transcribe `audio-input.ogg`
    (via `transcribe.py`'s endpoint) — keep this pluggable/optional.
  - Render `index.html` + `index.md` + `images/<step-id>.jpg` (named files, not
    base64). Respect `maskSegments` (don't emit redacted regions).
  - Emit NDJSON `{"type":"Completed","path":...}` under `--json` (match Cap's CLI).
- **Optional `--ai`:** a single OpenAI-compatible "format pass" that cleans caption
  text into step text. Off by default. (Reuse `structure.py`'s client pattern.)
- **Draw the boundary clearly:** the deterministic generator above = the
  **upstream candidate**. The **companion analytical layer** (tab detection,
  decisions/contradictions/open-questions item breakdown, multi-agent review)
  stays separate (keep `detect_tabs.py` / the analysis path as the companion, not
  part of `capguide`). Document this split in code + the prototype README.
- Fold the scattered config (offsets, model/endpoint URLs, crop params) into one
  place; remove dead/experimental bits; add docstrings + a short `spike/CAPGUIDE.md`
  usage doc. Don't delete the existing scripts the companion layer needs; refactor
  cleanly (shared helpers ok).

### B. Ground the design in Cap's actual repo
Clone `CapSoftware/Cap` (read-only) and confirm, citing file paths:
- crate layout (`crates/*`), how `apps/cli` defines subcommands (clap + NDJSON;
  read the `export` command as the template for `guide`), `cap-project` config/meta
  types, and `CONTRIBUTING.md` / code style / DCO or CLA requirements.
- Produce a **port map**: each prototype function → target Rust module in a new
  `crates/guide` (`cap-guide`) + a `cap guide` subcommand in `apps/cli`. Include a
  Rust **API sketch** (`Guide` / `Step` structs; the subcommand's clap args) — design
  only, no Rust implementation.

### C. Prepare upstream materials (drafts only — DO NOT POST)
Create an `upstream/` folder:
- `upstream/ISSUE.md` — concise feature request: problem (Cap stops at video; SOP/doc
  layer is owned by Scribe/Guidde), proposal (`cap guide`), why it fits Cap, link to
  the demo. Short, maintainer-friendly.
- `upstream/DISCUSSION.md` — RFC-style: motivation, design (crate + subcommand,
  reuse of zoomSegments/cursor/captions), CLI surface, non-goals, alternatives,
  AGPL/credit note, explicit "we have a working prototype + will PR if welcomed."
- `upstream/PR-PLAN.md` — the eventual PR's scope (crate, subcommand, tests, docs),
  the port map from B, and a checklist. State clearly: **PR deferred — not now.**
- `upstream/demo/` — generate `index.html` + `index.md` + `images/` from a
  **non-sensitive** recording (use the Microfactory app demo or the short Desktop
  `.cap`; **do not use client recordings** — Acme Corp/Acme Learning). This is the demo
  to attach to the issue/discussion.

## 4. Constraints
- **No GitHub PR/issue/discussion submission in this task** — drafts only.
- **AGPLv3** for anything destined upstream; keep the deterministic generator
  cleanly separable from the companion analytical layer.
- **Privacy:** AI must be optional and local-friendly; never require cloud.
- **Don't break** the existing companion pipeline; `spike-output/` stays gitignored;
  never commit recordings/media (see `.gitignore`).
- Keep the Python reference impl a faithful, portable mirror of the intended Rust
  surface (so the later port is mechanical).

## 5. Acceptance criteria / verification
1. `capguide <a .cap dir> --out <tmp> --format both` produces `index.html` +
   `index.md` + `images/` from a `.cap` **with no AI** (deterministic), and again
   **with `--ai`** for cleaned step text. Open the HTML; screenshots are auto-framed.
2. The companion analytical layer still runs unchanged.
3. `upstream/ISSUE.md`, `DISCUSSION.md`, `PR-PLAN.md`, and `demo/` exist and are
   coherent; the port map cites real Cap repo paths.
4. A short summary of what changed + what's ready to submit (and explicitly what was
   NOT done: no PR/issue posted).

## 6. Deliverables checklist
- [ ] Tightened `capguide` reference impl (deterministic + optional `--ai`), config
      consolidated, documented (`spike/CAPGUIDE.md`).
- [ ] Clear code/doc boundary: upstream-candidate core vs companion analysis.
- [ ] Cap repo study + port map + Rust API sketch.
- [ ] `upstream/ISSUE.md`, `upstream/DISCUSSION.md`, `upstream/PR-PLAN.md`.
- [ ] `upstream/demo/` generated from a non-sensitive recording.
- [ ] Summary of changes; confirmation that nothing was posted to GitHub.

---

## 7. Starter drafts (refine — do NOT ship as-is)

Use these as the basis for `upstream/ISSUE.md` and `upstream/DISCUSSION.md`.
Before finalizing: verify every Cap-repo claim against the cloned source, match
Cap's issue/discussion **templates** if they have them (`.github/`), confirm the
naming (`cap guide` vs `cap doc`), attach the generated demo, and check
`CONTRIBUTING.md` for DCO/CLA + the right place to propose features.

### 7a. Issue draft (`upstream/ISSUE.md`)

```markdown
**Feature: `cap guide` — generate an illustrated step / SOP doc from a recording**

### Problem
Cap produces beautiful recordings and transcripts, but stops there. The
"turn a recording into a step-by-step guide / SOP document" layer is currently
owned by tools like Scribe, Tango, and Guidde — all cloud-hosted, browser-first,
and with lower-fidelity screenshots than Cap already captures. Cap users who want
a doc (onboarding, SOPs, support articles) export the video and rebuild steps by
hand elsewhere.

### Proposal
Add a `cap guide <project.cap>` subcommand that renders a self-contained,
illustrated step/SOP document (`index.html` + `index.md` + `images/`) from data
Cap already has — cursor clicks/moves, `timeline.zoomSegments`, and captions.

```
cap guide <project.cap> [--out <dir>] [--format html|md|both] [--ai <openai-url>] [--json]
```

- **Deterministic by default, fully local** — steps come from `zoomSegments`
  (the moments Cap already judged important) + click events; each step's
  screenshot is auto-framed on the cursor focus (the polish Cap's zoom already
  computes); captions come from the recording's transcript.
- **AI optional** — `--ai <openai-compatible-url>` runs a single "format pass"
  to clean caption text into step instructions. Off by default; works with local
  models. No change to Cap's privacy posture.
- Sits beside `cap export` (export → video; guide → doc). Respects
  `maskSegments` (redaction). Same `--json`/NDJSON contract as `export`.

### Why it fits Cap
Cap already has the capture quality and all the signals needed; this is the
missing doc layer, and it keeps Cap's "beautiful, shareable, self-hostable" ethos.

### Status
We have a working prototype (reads real `.cap` recordings end-to-end) and a port
map to a `crates/guide` crate + `apps/cli` subcommand. **Happy to contribute a PR
(AGPLv3) if this is welcome upstream.** Demo doc attached: [link].

Would the maintainers be open to this? Any preferences on naming, crate boundary,
or the AI-provider abstraction before we open a PR?
```

### 7b. Discussion draft (`upstream/DISCUSSION.md`) — RFC

```markdown
# RFC: `cap guide` — recordings → illustrated step / SOP docs

## Motivation
Cap is the best open-source way to *capture* a workflow, but the output is a
video + transcript. Turning that into a **step-by-step guide / SOP** is a separate,
manual job today, and the tools that do it (Scribe, Tango, Guidde, Supademo) are
cloud, browser-first, and produce weaker screenshots than Cap already has. Cap is
uniquely positioned to own this: it captures any desktop app at high quality and
already computes cursor tracking + auto-zoom focus.

## Proposal
A new `cap guide` subcommand + `crates/guide` (`cap-guide`) that renders a
self-contained doc (`index.html` + `index.md` + `images/`) from a `.cap` project,
reusing existing data:
- **Steps** = `timeline.zoomSegments` (`mode: auto`) ∪ click-down events, deduped
  and time-ordered.
- **Auto-framed screenshots** — crop each step's frame to the cursor focus during
  its zoom segment (zoom amount → crop size). This is the same framing Cap's zoom
  already implies, applied to stills.
- **Captions** — from the recording's transcript/captions, grounded to each step.
- **Optional AI step-text** — `--ai <openai-compatible-url>`, a single format pass;
  off by default, local-friendly.

## CLI
`cap guide <project.cap> [--out <dir>] [--format html|md|both] [--ai <url> [--ai-model m]] [--json]`
— emits `{"type":"Completed","path":...}` under `--json`, matching `export`.

## Design / fit
- `cap-guide` is pure logic over `cap-project` types + cursor/captions/zoomSegments;
  frames via the existing decode path. The CLI subcommand mirrors `export`.
- AI is a thin pluggable OpenAI-compatible client behind a flag — no hard dep,
  no cloud requirement.

## Non-goals (for the first cut)
- No new editor UI (CLI-first; a desktop "Generate Guide" button can come later and
  shell the same crate).
- No hosting/sharing changes (reuse `cap upload`).
- AI is never required.

## Alternatives considered
- Third-party tool that consumes exported `.cap` files (works, but every Cap user
  re-solves it; worse discoverability; can't reuse internal types/zoom focus).
- Editor-only feature (higher effort; CLI-first is composable + agent-friendly,
  matching the existing `cap` CLI + bundled agent skill).

## Licensing
AGPLv3, same as Cap core. Credit shared.

## Questions for maintainers
1. Is a doc/SOP output something you'd want **upstream** (vs a plugin/companion)?
2. Naming: `cap guide` vs `cap doc` vs `export --guide`?
3. Crate boundary + where the AI-provider abstraction should live?
4. Anything in the project/render APIs we should build on rather than around?

## Status
Working prototype against real recordings; port map + crate API sketch ready.
We'll open a PR if there's appetite. Demo: [link].
```
