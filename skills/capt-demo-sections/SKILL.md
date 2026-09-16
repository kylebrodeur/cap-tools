---
name: capt-demo-sections
description: Record a complete product demo take with verified beats, style it, export once, and cut labeled sections for a demo timeline using cap-tools. Use when recording scripted product walkthroughs, checking a take's completeness, or producing per-beat/section clips for video assembly.
metadata:
  requires: Cap Desktop 0.6.0+ with `cap` on PATH; cap-tools checkout for `capt`
---

# Demo takes: verified beats → styled export → labeled sections

The whole-take-then-sections pipeline: record the WHOLE walkthrough once,
verify every scripted beat ran, style the full take, export once, then cut
labeled sections. Never record per-section — sections are cut from the
styled export afterwards, so re-splitting never requires re-recording.

## 1. Record with verified beats

```bash
uv run capt record <url> --steps beats.json --screen <id> [--window <id>] \
  [--storage-state state.json | --user-data-dir <profile>] [--until-stopped]
```

Every step is a beat: `{label}:start` / `{label}:ok` / `{label}:fail` marks
go into the events sidecar, and a completeness report lands next to the
take as `<name>.beats.json`:

```json
{"complete": true, "beats": [
  {"index": 0, "label": "open-project", "action": "click",
   "elapsed_s": 1.5, "beat_s": 0.4, "ok": true, "error": null}]}
```

- A failed beat **fails the take loudly** (recording finalized, error names
  the exact beat) — never continue styling a broken take.
- Every Playwright call has a timeout (default 20s; per-step
  `"timeout"` in ms overrides) — a dead selector can't hang the take.
- Beat `elapsed_s` is anchored to the recording's own timeline, so beat
  boundaries line up with the exported MP4.


### Recording the installed PWA app shell (not a fresh Chromium)

`capt record` launches its own Chromium by default. To record the real
installed PWA (e.g. a Chrome app-mode window), attach over CDP:

```bash
# 1. launch the PWA shell with a debugging port (app-mode, any URL):
open -na "Google Chrome" --args "--app=http://localhost:8080" \
  "--remote-debugging-port=9222" "--user-data-dir=/tmp/pwa-profile"
# 2. find the app window (fresh ID each launch — never cache it):
cap record windows --json          # the window named after the app
# 3. record that window while capt drives the SAME instance over CDP:
uv run capt record --window <id> --steps beats.json \
  --cdp http://localhost:9222 --out recordings
```

`--cdp` attaches to the running browser (disconnects after the take,
never closes it) — the capture shows the actual app shell. Quit any other
Chrome instance first: the profile lock and window enumeration both
misbehave with two running.

On Windows, run capt natively on Windows (never CDP across the WSL boundary
— Chrome's WebSocket resets unpredictably; see docs/FINDINGS.md §7). Full
PowerShell runbook: `docs/windows-pwa-capture-runbook.md` in cap-tools.

## 2. Check completeness before styling

```bash
python3 -c 'import json; b=json.load(open("recordings/take.beats.json")); \
  print("complete:", b["complete"]); \
  [print(" FAIL", x["label"], x["error"]) for x in b["beats"] if not x["ok"]]'
```

## 3. Style the full take (effects live here, not per section)

```bash
uv run capt scene apply recordings/take.cap recordings/take.events.json \
  --style reveal|punch|orbit --yes          # 3D camera scene (see capt-3d-scenes)
uv run capt zoom apply recordings/take.cap recordings/take.events.json
uv run capt config recordings/take.cap --preset gradient|animated   # background
```

## 4. Export once (mind the first-export gotcha)

The FIRST `cap export` of a fresh `.cap` strips `camera3dSegments` and
renders without the pose — export a throwaway warmup first, re-apply the
scene, then export for real. From the second export on it renders
deterministically.

```bash
cap export recordings/take.cap /tmp/warmup.mp4 --json      # if never exported
uv run capt scene apply recordings/take.cap recordings/take.events.json --style punch --yes
cap export recordings/take.cap recordings/take-styled.mp4 --json
```

## 5. Cut labeled sections

`cap export` ignores timeline trim headlessly (verified 0.6.0), so cuts are
ffmpeg post-export — re-cuttable any time without re-rendering:

```bash
uv run capt section list recordings/take.beats.json        # preview boundaries
uv run capt section cut recordings/take-styled.mp4 \
  recordings/take.beats.json --out demo-sections
#    → demo-sections/take.<beat-label>.mp4 (CRF 18 re-encode, frame-accurate)
```

Section sources: a `.beats.json` (beat-per-section), an events sidecar
(manual marks / global-capture clicks), or hand-written
`[{"name", "start_s", "end_s"}]` for arbitrary splits. `--stream-copy` for
fast rough cuts (keyframe-aligned, not frame-accurate).
If a beats report mixes named script beats with auto-labeled action/wait
beats, pass `--labeled-only` to `section list`/`cut` to keep only the named
beats (each section then spans its full paced window, next labeled beat to
next labeled beat).

## Timing

Beat pacing belongs in the steps file: `{"action": "wait", "ms": N}` after
each action, or a paced driver script under `capt record --steps`. Beat
sections inherit that pacing exactly. Effects that animate within a section
(e.g. orbit's tiltY sweep) animate inside the cut — pick style and section
boundaries together.