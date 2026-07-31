# Playbook — testing "Record a multi-step walkthrough with automatic zoom"

Validates, end to end on a real Cap install, the workflow proposed in the
`upstream/` PR branch (`apps/web/content/docs/agents/workflows.mdx`,
branch `agents-workflows-auto-zoom-recording` on the `kylebrodeur/Cap` fork)
before it gets pushed and opened as a real PR.

The upstream doc is tool-agnostic — any agent can do the "read config, build
segments, merge, confirm, write" steps itself with plain `cap` commands. This
repo provides a reference implementation: the `capt record` command with
`--marker-source steps+global-capture` and `--export-to` support now integrates
marking, zoom building, merging, and export into a single operation (see
`capt/record/beat.py`, `capt/cli.py`). Testing with this command validates the
technique works end-to-end without manual multi-step orchestration.

## What this validates

- `capt record` with `--marker-source steps+global-capture` captures real user
  interactions (clicks, keystrokes) without requiring manual mark entry.
- Zoom segments built from captured markers land where you'd expect when
  exported (i.e. the `pre_seconds`/`hold_seconds` defaults in
  `build_zoom_segments` feel right, not too early/late/short).
- Zoom segment merging into the existing config doesn't clobber other config
  fields (background, camera, cursor, etc. from whatever you'd already set
  in Studio).
- The `--export-to` flag on `capt record` produces an export that shows
  auto-zoom at the marked moments.

If any step feels off, that's a reason to tune the workflow doc (or
`build_zoom_segments`'s defaults in `capt/zoom.py`) before submitting
the PR — not something to paper over.

## Prerequisites

- Cap Desktop installed, with at least one **Studio**-mode recording capability
  (not Instant mode — Instant recordings have no per-stream cursor/zoom data).
- `cap` CLI resolvable — from WSL, `source skills/cap-cli/setup.sh` first (or
  `cap agents install` per the redirect noted in that skill's `SKILL.md`).
- This repo's Python env: `uv sync` (installs `capt` + the new `pytest` dev
  dependency; already verified with `uv run pytest tests/` — 10/10 passing for
  the pure `build_zoom_segments`/`merge_zoom_segments` logic before you touch
  a real recording).

## Steps

1. **Preflight and find a screen ID**

   ```bash
   capt preflight --marker-source steps+global-capture
   cap targets --json
   ```

   `capt` has no `doctor` command of its own — `capt preflight` is the real
   equivalent: it checks `cap doctor`/`cap targets` internally, plus (since
   this plan) the macOS Input Monitoring permission gate when
   `--marker-source` includes `global-capture`. Confirm all gates pass, then
   note a screen ID from `cap targets --json`'s `screens` list — `capt record`
   needs one explicitly (there's no default-primary-screen fallback in this
   codebase's usage; every example, including Cap's own docs, always passes
   `--screen`).

2. **Run the one-shot recording with auto-zoom and export**

   In a single command, `capt record` now handles marking, zoom-building, merging,
   and export. The `--marker-source steps+global-capture` flag captures every real
   click and keystroke (plus Cmd+Shift+M for manual labeled marks) while you drive
   the walkthrough by hand — replacing the old manual `capt zoom mark` step entirely:

   ```bash
   capt record https://example.com --out recordings --screen <screen-id> --marker-source steps+global-capture --export-to test-walkthrough.mp4 --json
   ```

   **What this does:**
   - Records the screen capture at the target URL (or local server).
   - Listens for every real user interaction (clicks, keyboard) and Cmd+Shift+M marks.
   - Internally builds zoom segments around each marked moment (0.5s before, 2.5s after by default).
   - Merges the zoom segments into the project config without clobbering other settings.
   - Exports directly to `test-walkthrough.mp4`.

3. **Perform the walkthrough**

   While the command is running, interact with the screen normally:
   - Click, type, and navigate as you would in a typical walkthrough.
   - Press Cmd+Shift+M at meaningful moments if you want to add explicit labeled marks
     (optional — every real click is already captured).
   - When done, the export completes automatically.

4. **Watch `test-walkthrough.mp4` and verify:**
   - Zoom kicks in ~0.5s before each marked moment and holds ~2.5s after it
     (the `build_zoom_segments` defaults) — if timing feels off, that signals a need
     to tune the defaults in `capt/zoom.py`, not just this one run.
   - Segments for markers placed close together merge into one continuous zoom
     instead of jarring in/out/in.
   - Anything you'd already configured in Studio (background, camera, cursor style)
     survived — this is what `merge_zoom_segments` is for.

## If it all checks out

The documented workflow is validated against a real recording. At that point:
push the `agents-workflows-auto-zoom-recording` branch to the
`kylebrodeur/Cap` fork and open the PR against `CapSoftware/Cap` — nothing
about the PR content depends on `capt`; it only had to prove the technique
works.

## If something's off

Note exactly what (wrong timing, clobbered fields, missed markers) — that feeds
back into either `capt/record/beat.py`'s defaults or a wording fix in the
workflow doc itself before it goes upstream.
