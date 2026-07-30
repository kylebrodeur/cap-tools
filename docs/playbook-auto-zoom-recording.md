# Playbook — testing "Record a multi-step walkthrough with automatic zoom"

Validates, end to end on a real Cap install, the workflow proposed in the
`upstream/` PR branch (`apps/web/content/docs/agents/workflows.mdx`,
branch `agents-workflows-auto-zoom-recording` on the `kylebrodeur/Cap` fork)
before it gets pushed and opened as a real PR.

The upstream doc is tool-agnostic — any agent can do the "read config, build
segments, merge, confirm, write" steps itself with plain `cap` commands. To
make this testable without hand-writing JSON each time, this repo now ships a
small reference implementation of that exact sequence: `capt zoom mark` /
`capt zoom apply` (see `capt/zoom.py`, `capt/cli.py`). Testing with these
commands is testing the documented technique, not a Cap-specific feature —
nothing here is upstream material itself.

## What this validates

- `cap record start --detach` → collecting markers during the recording →
  `cap record stop` → `cap project validate` all work as described.
- Zoom segments built from real elapsed-time markers land where you'd expect
  when exported (i.e. the `pre_seconds`/`hold_seconds` defaults in
  `build_zoom_segments` feel right, not too early/late/short).
- `cap project config get` → merge → `cap project config set` round-trips
  correctly and doesn't clobber other config fields (background, camera,
  cursor, etc. from whatever you'd already set in Studio).
- The export actually shows auto-zoom at the marked moments.

If any step feels off, that's a reason to tune the workflow doc (or
`build_zoom_segments`'s defaults) before submitting the PR — not something to
paper over.

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

1. **Preflight**

   ```bash
   cap doctor --json
   cap targets --json
   ```

   Confirm `captureReady: true` and at least one screen target.

2. **Start a detached recording**

   ```bash
   cap record start --screen <screen-id> --detach --json
   ```

   Note the returned `recordingId` and `path`.

3. **Collect markers while you drive the walkthrough**

   In a second terminal, before (or right as) you start performing the steps
   on screen:

   ```bash
   uv run capt zoom mark --out events.json
   ```

   Type a short label and press Enter at each meaningful moment (e.g.
   `opened-settings`, `toggled-dark-mode`, `clicked-save`). Press Ctrl-D when
   the walkthrough is done — this writes `events.json`.

4. **Stop the recording**

   ```bash
   cap record stop --id <recording-id> --json
   ```

   Confirm the response reports `recordingMetaExists: true`.

5. **Validate the project**

   ```bash
   cap project validate <path.cap> --json
   ```

6. **Build and apply zoom segments**

   ```bash
   uv run capt zoom apply <path.cap> events.json
   ```

   Review the printed proposed segments (this is the "show the merged config
   before writing" step from the workflow doc) — confirm when prompted, or
   pass `--yes` to skip the prompt once you trust it.

7. **Export**

   ```bash
   cap export <path.cap> --output test-walkthrough.mp4 --json
   ```

8. **Watch `test-walkthrough.mp4` and check:**
   - Zoom kicks in ~0.5s before each marked moment and holds ~2.5s after it
     (the `build_zoom_segments` defaults) — adjust `--amount` or, if the
     timing itself feels wrong, that's a signal to change the defaults, not
     just this one run.
   - Segments for markers placed close together merged into one continuous
     zoom instead of jarring in/out/in.
   - Anything you'd already configured in Studio (background, camera,
     cursor style) survived — this is what `merge_zoom_segments` is for.

## If it all checks out

The documented workflow is validated against a real recording. At that point:
push the `agents-workflows-auto-zoom-recording` branch to the
`kylebrodeur/Cap` fork and open the PR against `CapSoftware/Cap` — nothing
about the PR content depends on `capt`; it only had to prove the technique
works.

## If something's off

Note exactly what (wrong timing, clobbered fields, confusing confirmation
step) — that feeds back into either `capt/zoom.py`'s defaults or a wording fix
in the workflow doc itself before it goes upstream.
