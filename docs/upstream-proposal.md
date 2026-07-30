# RFC (draft): `cap doc` — generate an illustrated step / SOP doc from a recording

> A tightened system designed to be **contributed upstream to Cap** (AGPLv3),
> not maintained as a fork. Pairs with [PRODUCTIZATION.md](PRODUCTIZATION.md).
> Status: draft for discussion / for opening an issue with CapSoftware.

## Status update — 2026-07-30 (checked against CapSoftware/Cap on GitHub)

Re-verified this RFC against Cap's current source (`apps/cli/src/*.rs`, commit history via
`gh api`) and public docs (`cap.so/docs/agents`). Two things changed since this was drafted
(2026-06-27):

- **Renamed `cap guide` → `cap doc` throughout this doc.** `cap guide` was already the
  agent capability-manifest command *before* this RFC was written (added 2026-06-04,
  commit `db23a7f`) — the name collision existed at draft time, we just hadn't checked
  upstream first. It only got more entrenched since: `guide.rs` was extended again on
  2026-07-18 (commit `a9dbcdc`) alongside a new `cap agents install` command. `cap doc`
  (an alternative this doc already floated in `upstream-agent-brief.md`) is open as of this
  check.
- **The doc/SOP gap this RFC targets is still open.** Despite substantial CLI growth since
  June (`caps`, `organizations`, `library`, `notifications`, `analytics`, `developers`,
  `jobs`, `automations`, `mcp serve`, `agents install` — see `apps/cli/src/` for the full
  list), none of it is a recording→doc/SOP generator. This RFC's core proposal is still a
  genuine, unclaimed gap.
- **New context worth citing in the issue/discussion:** Cap shipped a full agent/MCP
  ecosystem on 2026-07-18 (`cap agents install --target codex|claude|cursor --component
  skill|mcp|all`, documented at `cap.so/docs/agents`). `cap doc` would fit naturally as
  another command that same MCP server/skill could expose — worth a line in the RFC's
  "why it fits Cap" section, since it strengthens the case that Cap is actively investing
  in exactly this kind of composable, agent-friendly surface.

## Status update — 2026-07-30 (maintainer response, supersedes the issue/Discussion plan above)

Kyle emailed Richie (CapSoftware, author of the `guide.rs`/agents commits verified above)
directly, rather than going through the issue+Discussion process this doc assumed. Richie's
reply: **go ahead and open a pull request with "agent workflows and tools for Cap."**

This changes the plan in a few ways, not yet fully worked out:
- We have a direct maintainer green light — the issue-first, "would you be open to this?"
  framing in `upstream/ISSUE.md` is no longer the operative path (a PR is). That draft can
  still be reused as PR-description material.
- **"Agent workflows and tools" is broader than just `cap doc`.** It's not yet clear whether
  Richie means: (a) the `cap doc` recording→SOP feature specifically, (b) our `skills/cap-cli`
  WSL-bridge + agent-integration work, (c) the record-automation ("beat") half of this repo,
  or (d) some combination — needs a scoping pass before building the actual PR branch.
- The "GitHub Discussions is disabled / CONTRIBUTING.md routes to Discord" finding above is
  now moot for this feature (no issue/Discussion needed — direct maintainer buy-in supersedes
  it), but may still be useful context if other features get proposed later.

**Not yet done:** scoping exactly what "agent workflows and tools" should include in the PR,
and building it. This note is a placeholder pending that scoping conversation.

## Summary

Add a **`cap doc <project.cap>`** CLI subcommand (backed by a new
**`crates/doc`** = `cap-doc`) that turns a recording into a self-contained,
illustrated **step-by-step guide / SOP** (`index.html` + `index.md` + `images/`),
reusing data Cap already captures: cursor clicks/moves, `timeline.zoomSegments`,
and captions. **Deterministic by default**; optional AI step-text via a pluggable
OpenAI-compatible endpoint (local-friendly, off by default).

## Motivation

- Cap nails capture and beautiful recordings, but stops at **video + transcript**.
  The **document / SOP** layer is owned by Scribe, Tango, Guidde, Supademo — all
  cloud, browser-first, with lower-fidelity screenshots.
- Cap already has everything needed to win that layer: high-quality frames, cursor
  clicks + moves, `zoomSegments` (the moments Cap already judged important), and
  captions. A guide output turns those into **auto-framed screenshots** — the
  Screen-Studio polish bar, applied to docs.
- It sits naturally beside `cap export` (export → video; guide → doc), is
  self-host / privacy friendly, and extends Cap into onboarding/training/SOP
  use-cases without leaving its ethos.
- Cap already invests in exactly this kind of composable, agent-friendly surface —
  `cap agents install` + `cap mcp serve` (shipped 2026-07-18) mean a `cap doc` command
  would slot straight into the same MCP server and skill agents already use for `cap`.

## What it produces

A folder: `index.html` + `index.md` + `images/`, one step per meaningful moment:
- **Screenshot**, auto-framed using `zoomSegments` + cursor focus (tight crop on
  what matters; full frame when no zoom applies).
- **Caption** from the nearest caption segment, grounded to the step timestamp.
- Optional **AI-cleaned step text** ("Click the Settings tab") when `--ai` is set.
- Respects `maskSegments` (redaction); can reuse `annotations` / `textSegments`.

## Step derivation

Steps = union of **(a)** `zoomSegments` (`mode: auto` = Cap's important moments)
and **(b)** click-down events from cursor data — deduped + debounced, ordered by
time. Each step's focal region = dwell-weighted cursor position during its window
(the zoom already follows the cursor, so this matches Cap's own framing).

## Design / fit with Cap's architecture

- **New crate `crates/doc` (`cap-doc`)** — pure logic: read `RecordingMeta`
  (`recording-meta.json`) + cursor + captions + `project-config.json`
  (`timeline.zoomSegments`) → a `Guide { steps: [Step { t, crop, caption, text }] }`
  → render HTML + Markdown. Reuses `cap-project` types; pulls frames via the
  existing decode path / `cap-rendering` (or ffmpeg fallback).
- **CLI subcommand in `apps/cli`** — `cap doc`, same `clap` + NDJSON / `--json`
  contract as `export`/`record` (emits `{"type":"Completed","path":...}`).
- **AI optional + pluggable** — off by default (deterministic, fully local). With
  `--ai <openai-compat-url>`, one "format pass" turns captions into clean step
  text. Preserves Cap's privacy posture; works with local Ollama or any endpoint.

## CLI surface (proposed)

```
cap doc <project.cap> [--out <dir>] [--format html|md|both]
                        [--ai <url> [--ai-model <m>]] [--json]
```

## Non-goals (keep the MVP tight)
- **No new editor UI** — CLI-first. The desktop app can later add a "Generate
  Guide" button that shells the same crate.
- **AI is optional**, never required.
- **No hosting/sharing changes** — reuse `cap upload`.

## We've already prototyped it (de-risks the PR)

Our spike implements every piece against real `.cap` recordings; porting to a
crate/subcommand is the work:

| Prototype (this repo) | Maps to in `cap-doc` |
|---|---|
| `spike/cap_ingest.py` (clicks → steps + frames) | step derivation + frame extraction |
| cursor-region + `zoomSegments` framing | auto-framed screenshot crop |
| `spike/build_walkthrough_doc.py` (HTML+MD, named images) | renderer |
| `spike/structure.py` (transcript → clean text, OpenAI-compatible) | optional `--ai` format pass |

Validated end-to-end on an 18-min recording (correct tab grouping, transcript-
anchored steps, cursor-region overlays, HTML + Markdown).

## The tightened system (end to end)

```
cap record ──▶ .cap ──┬─▶ cap export  ──▶ polished zoomed video      [exists]
                      └─▶ cap doc    ──▶ illustrated SOP (HTML/MD)   [THIS RFC → upstream]

  guide-tool companion (ours, optional, builds ON cap doc):
      deep "review analysis" — narrated walkthrough → decisions /
      contradictions / open questions, tab-aware grouping, multi-agent
      review, extra exports.                                          [our product layer]
```

**Clean separation:** the **deterministic guide generator** goes upstream (gives
every Cap user the doc/SOP feature, AGPL, full credit shared). Our **analytical
layer** (which turns a *spoken review* into structured decisions/contradictions/
open-questions) stays a companion that consumes `cap doc` output — no conflict,
clear value line.

## Licensing / contribution
- **AGPLv3** (matches Cap core; only `cap-camera*`/`scap-*` are MIT).
- Process: open a GitHub **issue/RFC** on `CapSoftware/Cap` first (link a demo
  built from this spike) → if welcomed, PR the `cap-doc` crate + `cap doc`
  subcommand, MVP (deterministic) first, `--ai` step-text as a follow-up.

## Next steps
1. Open the issue/RFC on `CapSoftware/Cap` with a short demo (an `index.html`
   generated from one of our recordings).
2. Draft the `cap-doc` crate API (`Guide` / `Step` model) + `cap doc` subcommand.
3. PR the deterministic MVP; add `--ai` as a flagged follow-up.
