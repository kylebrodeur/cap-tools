# RFC (draft): `cap guide` — generate an illustrated step / SOP doc from a recording

> A tightened system designed to be **contributed upstream to Cap** (AGPLv3),
> not maintained as a fork. Pairs with [PRODUCTIZATION.md](PRODUCTIZATION.md).
> Status: draft for discussion / for opening an issue with CapSoftware.

## Summary

Add a **`cap guide <project.cap>`** CLI subcommand (backed by a new
**`crates/guide`** = `cap-guide`) that turns a recording into a self-contained,
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

- **New crate `crates/guide` (`cap-guide`)** — pure logic: read `RecordingMeta`
  (`recording-meta.json`) + cursor + captions + `project-config.json`
  (`timeline.zoomSegments`) → a `Guide { steps: [Step { t, crop, caption, text }] }`
  → render HTML + Markdown. Reuses `cap-project` types; pulls frames via the
  existing decode path / `cap-rendering` (or ffmpeg fallback).
- **CLI subcommand in `apps/cli`** — `cap guide`, same `clap` + NDJSON / `--json`
  contract as `export`/`record` (emits `{"type":"Completed","path":...}`).
- **AI optional + pluggable** — off by default (deterministic, fully local). With
  `--ai <openai-compat-url>`, one "format pass" turns captions into clean step
  text. Preserves Cap's privacy posture; works with local Ollama or any endpoint.

## CLI surface (proposed)

```
cap guide <project.cap> [--out <dir>] [--format html|md|both]
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

| Prototype (this repo) | Maps to in `cap-guide` |
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
                      └─▶ cap guide   ──▶ illustrated SOP (HTML/MD)   [THIS RFC → upstream]

  guide-tool companion (ours, optional, builds ON cap guide):
      deep "review analysis" — narrated walkthrough → decisions /
      contradictions / open questions, tab-aware grouping, multi-agent
      review, extra exports.                                          [our product layer]
```

**Clean separation:** the **deterministic guide generator** goes upstream (gives
every Cap user the doc/SOP feature, AGPL, full credit shared). Our **analytical
layer** (which turns a *spoken review* into structured decisions/contradictions/
open-questions) stays a companion that consumes `cap guide` output — no conflict,
clear value line.

## Licensing / contribution
- **AGPLv3** (matches Cap core; only `cap-camera*`/`scap-*` are MIT).
- Process: open a GitHub **issue/RFC** on `CapSoftware/Cap` first (link a demo
  built from this spike) → if welcomed, PR the `cap-guide` crate + `cap guide`
  subcommand, MVP (deterministic) first, `--ai` step-text as a follow-up.

## Next steps
1. Open the issue/RFC on `CapSoftware/Cap` with a short demo (an `index.html`
   generated from one of our recordings).
2. Draft the `cap-guide` crate API (`Guide` / `Step` model) + `cap guide` subcommand.
3. PR the deterministic MVP; add `--ai` as a flagged follow-up.
