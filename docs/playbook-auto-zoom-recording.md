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

- Cap Desktop installed, **running**, and in **Studio** mode (Instant
  recordings have no per-segment cursor/zoom data). Launch it with
  `open -a Cap`. `curl -fsSL https://cap.so/install-cli.sh | sh` installs
  both the desktop app and the `cap` CLI shim.
- This repo's Python env: `uv sync`. Run its commands as `uv run capt …`;
  no virtualenv activation is required.
- macOS Input Monitoring permission granted to whatever terminal runs
  `capt` — `uv run capt preflight` (below) checks this and tells you if it's
  missing.

## The short path: `capt demo`

For a live, narrated walkthrough — no pre-written script, no fixed
duration — `capt demo` wraps everything below into one command:

```bash
uv run capt demo my-walkthrough                       # screen + mic auto-detected
uv run capt demo my-walkthrough --pick                # interactive window/screen picker
uv run capt demo my-walkthrough --window <id>         # one window instead of the full screen
```

With `--pick` (or `capt record --pick`), `capt` lists every live window
(PWA apps show under their own name — e.g. `ReelBinder`) plus the screens,
and you type the number. Filter by *owner*, not title: a Chrome tab titled
"ReelBinder…" is not the PWA; the entry owned by `ReelBinder` is.

It runs preflight, picks the primary screen (or first microphone) from
`cap targets --json` unless you override them, then records with real
click-tracking (`--marker-source global-capture`) until you press
**Ctrl-C in this terminal**. `capt` catches it as a graceful stop request,
stops the exact detached Cap CLI session, then finishes the sidecar, zoom,
validation, and export. When it's done:

```
✓ Recorded: recordings/my-walkthrough.cap
  Exported: recordings/my-walkthrough.mp4
  Next: capt guide recordings/my-walkthrough.cap --format both
```

### Today's target: ReelBinder (Chrome PWA)

The installed PWA (`~/Applications/Chrome Apps.localized/ReelBinder.app`)
shows up as its own window target, so you can record just the app instead
of the whole desktop:

```bash
cd ~/workspace/slate
open -a Cap
uv run --project ~/workspace/__Tools/cap-tools \
  capt demo reelbinder-demo --pick \
  --out ~/workspace/slate/recordings
```

Click through the app as normal; every click becomes a zoom marker and
Cmd+Shift+M adds a labeled mark. Press **Ctrl-C in this terminal** to stop
safely. The completed take contains a zoomed MP4, `.cap`, and
`recordings/reelbinder-demo.events.json`.

Skip to [Watch the output](#watch-the-output) below. The rest of this doc
is the manual, step-by-step version — useful if you want more control than
`capt demo` gives you, or if you're validating the technique itself rather
than just using it.


## Manual steps

1. **Preflight, then find a screen or window ID**

   ```bash
   open -a Cap
   uv run capt preflight --marker-source steps+global-capture
   cap targets --json
   ```

   Confirm every gate passes. `capt preflight` checks `cap` is resolvable,
   a screen target exists, Playwright's installed, the output dir is
   writable, and — on macOS, when `--marker-source` includes
   `global-capture` — that Input Monitoring is actually granted. Gate G8
   now shells out to `cap doctor` too: a missing screenRecording
   permission or `captureReady: false` (stale ScreenCaptureKit state)
   fails fast here instead of wasting a take. Doctor unavailable? It
   degrades to a warning.

   Take a screen ID from `cap targets --json`'s `screens` list, or a
   window ID from its `windows` list — `capt record` needs one explicitly
   passed via `--screen` or `--window` (there's no default-primary-screen
   fallback). Skip the ID lookup entirely with `--pick` (below).

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
   uv run capt record --screen <screen-id> \
     --marker-source global-capture --until-stopped \
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
   already captured automatically). When you're done, press **Ctrl-C in
   the same terminal that is running `capt`**. `capt` catches the interrupt
   rather than exiting, stops the exact detached session via
   `cap record stop --id <recordingId>`, then builds zoom segments, merges
   them into the project config, writes the sidecar, validates, and exports.

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
  {"action": "click", "selector": ".load-more", "count": 2},
  {"action": "mark", "label": "clicked-more-info-link"}
]
```

```bash
uv run capt record --screen <screen-id> --steps steps.json \
  --marker-source steps --export-to demo.mp4 --json
```

Each `goto`/`click`/`fill` and every explicit `mark` becomes a real event,
the same as a live click does — the resulting zoom segments and export
work identically either way. Playwright launches its own Chromium to drive
this, visible only when a step actually needs a real page (a `url`, or a
`goto`/`click`/`fill`) — pure `wait`/`mark` steps run it headless instead
of popping up an empty, unused browser window.

`--marker-source steps+global-capture` combines both: drive a scripted
setup, then keep capturing real clicks on top of it.

### Authenticated scripted recording (logged-in apps)

Playwright's browser starts logged-out. To script a take inside an app
that needs login (e.g. the ReelBinder PWA), hand the driver your session:

```bash
# option A: full Chrome profile — covers IndexedDB, service workers, PWAs
uv run capt record https://studio.reelbinder.app --out recordings \
  --user-data-dir "$HOME/Library/Application Support/Google/Chrome/Default" \
  --screen <screen-id> --steps steps.json --export-to demo.mp4

# option B: bare storage state (cookies + localStorage only)
uv run capt record ... --storage-state state.json
```

`--user-data-dir` wins when both are passed. Launch with the profile only
while Chrome is closed — Chromium locks the profile directory.

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
- `recordings/<name>.events.json` lists every captured event with its
  `elapsed_s` — your manual-marks are in there, ready to rename and
  re-apply (see [Command reference](#command-reference)).

Then turn the recording into an illustrated guide from the same `.cap`:

```bash
uv run capt guide recordings/my-walkthrough.cap --format both
```

## Command reference

| Command | What it does |
|---|---|
| `uv run capt preflight [--marker-source …] [--url <u>]` | Readiness gates (G1–G8), including `cap doctor` capture-readiness |
| `uv run capt demo <name> [--pick] [--window <id>]` | Live narrated take: preflight + auto screen/mic + real-click zoom + auto export; press Ctrl-C in this terminal to stop and finalize safely |
| `uv run capt record --pick` / `uv run capt record --window <id> --marker-source global-capture --until-stopped` | The same take, with manual control; Ctrl-C is graceful while waiting |
| `uv run capt record --steps steps.json [--screen <id>]` | Scripted, repeatable beat |
| `uv run capt record … --storage-state s.json` / `--user-data-dir <profile>` | Scripted beat inside a logged-in app |
| `uv run capt guide recordings/<name>.cap --format both` | Illustrated HTML + Markdown guide from a recording |
| `uv run capt guide recordings/<name>.cap --ai` | + decision/contradiction/open-question analysis (cap-guide-analysis) |
| `uv run capt zoom apply recordings/<name>.cap recordings/<name>.events.json` | Rebuild zoom from the events sidecar (e.g. after renaming manual-marks) |
| `uv run capt scene apply recordings/<name>.cap recordings/<name>.events.json --style orbit --yes` | Apply a 3D camera scene (Cap 0.6+) from the same sidecar |
| `uv run capt export recordings/<name>.cap out.mp4` | Export only (after config changes) |
| `uv run capt config recordings/<name>.cap --get` | Inspect project-config.json |

Every recording leaves `<name>.events.json` next to the `.cap` — the exact
click/mark timeline. Edit its labels (e.g. rename `manual-mark` to
`opened-contacts-sheet`), re-apply zoom, re-export.

## If it all checks out

The technique's validated against a real recording. The upstream doc
addition (`upstream/workflows-mdx-addition.md`) describes the same
pattern in Cap-native terms (`cap record start`/`stop`, manual zoom-segment
merge, `cap export`) for any agent to follow without `capt` — that's what's
ready to become a real PR against `CapSoftware/Cap`, once submitted.

## 3D scenes (Cap 0.6+)

Zoom segments crop toward the cursor; `timeline.camera3dSegments` moves the
whole camera in 3D instead (orbit/tilt/depth), and the two compose. The
schema, style guide (`reveal`/`punch`/`orbit`/`flat`), and geometry contract
live in [`skills/capt-3d-scenes/SKILL.md`](../skills/capt-3d-scenes/SKILL.md).

Verified live on 0.6.0 (2026-09-15): apply an orbit scene, export, and
frames inside the segment window differ on 60.8% of downscaled pixels —
the camera visibly swings (edge lean −5.6° → −22.9° across the window,
level again after the segment ends). One gotcha the testing surfaced:
**the first `cap export` of a fresh `.cap` strips `camera3dSegments` and
renders without the pose** (Cap's publish pass). Warm up with a throwaway
export, then apply the scene, then export for real:

```bash
cap export recordings/demo.cap /tmp/warmup.mp4 --json   # first-export publish pass
uv run capt scene apply recordings/demo.cap recordings/demo.events.json \
  --style orbit --duration 12 --yes
cap export recordings/demo.cap out.mp4 --json
# frame-difference check (see skill doc) or eyeball mid.png vs flat.png
```

All three styles verified this way: orbit (swing, 60.8%), reveal (static
lean-back, keystoned in-frame), punch (tilted inside each window, flat in
the gaps). Geometry gotchas that bite: `zoom` is camera *distance* (larger
= smaller on screen — decrease it to make the recording bigger, there's no
fov compensation), and only `tiltX/tiltY/rotateX/rotateY/fov/blur*` are
animatable tracks — not `roll`/`panX`/`panY`/`zoom`.

## Whole-take-then-sections workflow (demo timelines)

For a product demo you style after the fact, don't record per-section:
record the WHOLE take once, verify it, style it, export it once, then cut
labeled sections. `cap export` ignores timeline trim when driven headlessly
(verified 0.6.0 — a trimmed `timeline.segments[0].start/end` still exports
full length), so section splits happen on the exported MP4 with ffmpeg:

```bash
# 1. record the whole walkthrough (steps = verified beats)
uv run capt record https://app.example --steps beats.json \
  --screen <id> --until-stopped
#    → take.cap + take.events.json + take.beats.json ({"complete": bool, "beats": [...]})

# 2. check completeness BEFORE styling — every beat ok, or re-record
python3 -c 'import json; b=json.load(open("recordings/take.beats.json")); \
  print("complete:", b["complete"]); \
  [print(" FAIL", x["label"], x["error"]) for x in b["beats"] if not x["ok"]]'

# 3. style the full take (zoom + 3D scene, optional gradient background)
uv run capt scene apply recordings/take.cap recordings/take.events.json \
  --style punch --yes
uv run capt config recordings/take.cap --preset animated   # optional

# 4. export once, warmup first if this .cap never exported (see above)
cap export recordings/take.cap recordings/take-styled.mp4 --json

# 5. cut labeled sections for the demo timeline
uv run capt section list recordings/take.beats.json        # preview boundaries
uv run capt section cut recordings/take-styled.mp4 \
  recordings/take.beats.json --out demo-sections
```

Sections inherit the full take's effects; each section is a normal MP4
(re-encoded CRF 18 — frame-accurate, timeline-assembly safe). Re-cut with
different boundaries any time without re-rendering the styled export, or
hand-write a sections JSON (`[{"name", "start_s", "end_s"}]`) for arbitrary
splits that don't line up with beats.

## If something's off

- **Wrong zoom timing or clobbered config fields**: note exactly what, and
  feed it back into `capt/record/beat.py`'s defaults or a wording fix in
  the upstream doc draft.
- **A live recording fails with a display/decode error** (e.g. "no
  decodable frames", a bare `"display"` error): preflight's G8 gate now
  checks `cap doctor`'s capture-readiness before you record, but if you
  skipped preflight or it raced, run `cap doctor --json` and check
  `captureReady` / `screenCaptureKit`. A long-running Cap Desktop session
  can end up with stale ScreenCaptureKit state — quit and relaunch Cap
  Desktop, then re-check `cap doctor` before assuming it's a `capt` bug.
