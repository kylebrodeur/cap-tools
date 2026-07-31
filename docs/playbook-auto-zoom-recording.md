# Playbook — recording a walkthrough with automatic zoom

Every command below has been run for real on a macOS machine against a live
Cap install (most recently 2026-07-31, after a live-capture regression on
this machine turned out to be a stale ScreenCaptureKit session in Cap
Desktop itself — fixed by quitting and relaunching Cap, confirmed via
`cap doctor`'s `captureReady` field; not a `capt` bug, but worth knowing if
a live recording ever fails with a display/decode error for no obvious
reason).

This also validates the technique behind the `apps/web/content/docs/agents/
workflows.mdx` addition drafted in `upstream/workflows-mdx-addition.md` (not
yet a PR — see that file's header) before it's submitted upstream: any
agent can do the "track elapsed time, build zoom segments, merge, export"
steps itself with plain `cap` commands; this repo's `capt` is a reference
implementation proving the technique works end to end.

## Prerequisites

- Cap Desktop installed, in **Studio** mode (Instant recordings have no
  per-segment cursor/zoom data). `curl -fsSL https://cap.so/install-cli.sh | sh`
  installs both the desktop app and the `cap` CLI shim.
- This repo's Python env: `uv sync`.
- macOS Input Monitoring permission granted to whatever terminal runs
  `capt` — `capt preflight` (below) checks this and tells you if it's
  missing.

## The short path: `capt demo`

For a live, narrated walkthrough — no pre-written script, no fixed
duration — `capt demo` wraps everything below into one command:

```bash
capt demo my-walkthrough                       # screen + mic auto-detected
capt demo my-walkthrough --window <id>         # one window instead of the full screen
```

It runs preflight, picks the primary screen (or first microphone) from
`cap targets --json` unless you override them, then records with real
click-tracking (`--marker-source global-capture`) until **you stop it from
Cap's own UI** (menu bar icon / Studio's Stop button) — not a keypress, so
nothing you type or click during the demo itself can end the recording
early. When it's done:

```
✓ Recorded: recordings/my-walkthrough.cap
  Exported: recordings/my-walkthrough.mp4
  Next: capt guide recordings/my-walkthrough.cap --format both
```

Skip to [Watch the output](#watch-the-output) below. The rest of this doc
is the manual, step-by-step version — useful if you want more control than
`capt demo` gives you, or if you're validating the technique itself rather
than just using it.

## Manual steps

1. **Preflight, then find a screen or window ID**

   ```bash
   capt preflight --marker-source steps+global-capture
   cap targets --json
   ```

   Confirm every gate passes. `capt preflight` checks `cap` is resolvable,
   a screen target exists, Playwright's installed, the output dir is
   writable, and — on macOS, when `--marker-source` includes
   `global-capture` — that Input Monitoring is actually granted (it does
   **not** shell out to `cap doctor`; that's a separate, Cap-native
   diagnostic worth running yourself if a live recording ever behaves
   strangely — see the note at the top of this doc).

   Take a screen ID from `cap targets --json`'s `screens` list, or a
   window ID from its `windows` list — `capt record` needs one explicitly
   passed via `--screen` or `--window` (there's no default-primary-screen
   fallback).

2. **Start the recording**

   For a live, unscripted walkthrough (the case this playbook validates),
   use `--marker-source global-capture` (real clicks only, no Playwright)
   with `--until-stopped` — **the `--until-stopped` flag is required** for
   this to work as an interactive session. Without it, with no `--steps`
   to drive, the recording starts and immediately stops again — there's
   nothing else telling it to keep going. (Confirmed directly: the same
   command without `--until-stopped` finished in under 7 seconds end to
   end, with no window to actually interact with anything.)

   ```bash
   capt record --screen <screen-id> --marker-source global-capture --until-stopped \
     --mic "<device name>" --export-to test-walkthrough.mp4 --json
   ```

   (`--mic` is optional — omit it for a silent recording. Device names
   come from `cap targets --json`'s `mics` list. **The first time you use
   `--mic` (or `--camera`/`--system-audio`) on a given machine**, check
   `cap doctor --json`'s `permissions.microphone` field first — if it's
   `notDetermined` rather than `granted`, the recording will hang and then
   fail with "timed out waiting for the recording to start" instead of
   prompting for permission, since there's no interactive session to grant
   it from a backgrounded CLI call. Grant microphone access to Cap Desktop
   once via System Settings → Privacy & Security → Microphone, or trigger
   the permission prompt by starting one recording with `--mic` from Cap's
   own Studio UI first, then retry.)

3. **Perform the walkthrough**

   Click, type, and navigate as you normally would. Press Cmd+Shift+M at
   any moment for an explicit labeled mark (optional — every real click is
   already captured automatically). When you're done, **stop the
   recording from Cap's own UI** — its menu bar icon, or Studio's Stop
   button. The command finishes on its own once it notices (it polls
   `cap record status`, typically within about a second), builds zoom
   segments from every click it saw, merges them into the project config,
   and exports.

## Scripted recordings

For a repeatable beat instead of a live walkthrough — the same demo run
the same way every time — drive it with a `steps.json` file instead of
`global-capture`. Each step is one of `goto`/`click`/`fill`/`wait`/`mark`;
see `capt/record/steps.py` for the full schema. Example, verified live:

```json
[
  {"action": "goto", "url": "https://example.com"},
  {"action": "wait", "ms": 1000},
  {"action": "click", "selector": "a"},
  {"action": "mark", "label": "clicked-more-info-link"}
]
```

```bash
capt record --screen <screen-id> --steps steps.json --marker-source steps \
  --export-to demo.mp4 --json
```

Each `goto`/`click`/`fill` and every explicit `mark` becomes a real event,
the same as a live click does — the resulting zoom segments and export
work identically either way. Playwright launches its own Chromium to drive
this, visible only when a step actually needs a real page (a `url`, or a
`goto`/`click`/`fill`) — pure `wait`/`mark` steps run it headless instead
of popping up an empty, unused browser window.

`--marker-source steps+global-capture` combines both: drive a scripted
setup, then keep capturing real clicks on top of it.

## Watch the output

Open the exported MP4 and check:
- Zoom kicks in shortly before each real click and holds a couple of
  seconds after it (`build_zoom_segments`'s `pre_seconds`/`hold_seconds`
  defaults in `capt/zoom.py`) — if timing feels off, that's a signal to
  tune those defaults, not just re-record.
- Clicks placed close together merge into one continuous zoom instead of
  jarring in/out/in.
- Anything already configured in Studio (background, camera, cursor
  style) survived — `merge_zoom_segments` does a read-merge-write, never a
  blind overwrite.

Then turn the recording into an illustrated guide from the same `.cap`:

```bash
capt guide recordings/my-walkthrough.cap --format both
```

## If it all checks out

The technique's validated against a real recording. The upstream doc
addition (`upstream/workflows-mdx-addition.md`) describes the same
pattern in Cap-native terms (`cap record start`/`stop`, manual zoom-segment
merge, `cap export`) for any agent to follow without `capt` — that's what's
ready to become a real PR against `CapSoftware/Cap`, once submitted.

## If something's off

- **Wrong zoom timing or clobbered config fields**: note exactly what, and
  feed it back into `capt/record/beat.py`'s defaults or a wording fix in
  the upstream doc draft.
- **A live recording fails with a display/decode error** (e.g. "no
  decodable frames", a bare `"display"` error) despite `capt preflight`
  passing: run `cap doctor --json` and check `captureReady` /
  `screenCaptureKit`. A long-running Cap Desktop session can end up with a
  stale ScreenCaptureKit state that `capt preflight` doesn't catch (it only
  checks the Input Monitoring permission, not live capture health) — quit
  and relaunch Cap Desktop, then re-check `cap doctor` before assuming it's
  a `capt` bug.
