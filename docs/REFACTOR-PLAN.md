# Refactor Plan — Cap CLI Extension

Plan for refactoring `cap-cli-skill` from a thin WSL shim into a proper CLI
extension that agents and scripts can use for the full record → polish → export
→ assemble pipeline.

---

## Current state

The skill is a one-file WSL wrapper (`setup.sh`) that puts `cap-cli.exe` on
`$PATH` via a shell function. It works for basic `cap record` / `cap export`
invocations but has no helpers for:

- Browser automation (CDP, Chrome launch)
- Project config manipulation (zoom, background, cursor)
- Beat-based recording orchestration
- Video assembly
- Preflight / doctor checks
- Windows-native Playwright invocation

---

## Goals

1. **A single entry point** — one command (or small set of commands) that handles
   the full workflow without needing to know the internals.
2. **Generalized** — not tied to any specific app, URL, or beat structure. The
   caller provides those.
3. **Programmatic polish** — auto-zoom segments generated from Playwright event
   timestamps; no Studio required.
4. **WSL-first, Windows-native Playwright** — the skill runs from WSL but
   delegates browser automation to Windows-native Node/Playwright to avoid
   CDP/WebSocket reliability issues.
5. **Agent-friendly** — all commands emit `--json`, all errors are clear and
   actionable, all state is written to predictable paths.

---

## Proposed command surface

```
cap-ext record   <url> [options]       # full record-and-polish cycle
cap-ext beat     <name> <url> [opts]   # record one named beat
cap-ext polish   <project.cap> [opts]  # apply config (zoom, bg, cursor)
cap-ext export   <project.cap> [opts]  # export .cap → MP4
cap-ext assemble <manifest.json>       # stitch clips → final video
cap-ext preflight [url]                # check all deps
cap-ext config   <project.cap>         # read/write project-config.json
```

Or as a single Node.js CLI (`cap-ext` / `capx`) with subcommands.

---

## Architecture

```
cap-cli-skill/
  setup.sh                    # existing: puts cap on $PATH
  agent.sh                    # existing: verification for agents
  bin/
    cap-ext                   # main entry point (Node.js or bash dispatcher)
  lib/
    cap.js                    # cap CLI wrapper (JSON parsing, detach, retry)
    browser.js                # Chrome launch + CDP + Playwright helpers
    config.js                 # project-config.json builder / writer
    zoom.js                   # zoom segment generation from event timestamps
    preflight.js              # gate checks
    export.js                 # cap export wrapper with progress
    assemble.js               # ffmpeg assembly pipeline
  templates/
    config-clean.json         # minimal clean-export config template
    config-demo.json          # demo/presentation config template
  docs/                       # this directory
  SKILL.md                    # updated skill manifest
```

---

## Module breakdown

### `lib/cap.js` — Cap CLI wrapper

Handles the two reliability problems with `cap-cli.exe` from WSL:

1. **Detached spawn** — `cap record start --detach` must be spawned to a temp
   file; `execSync` blocks forever. Returns the parsed `{recordingId, pid}`.
2. **JSON parsing** — output can be multi-line pretty-printed or prefixed with
   log lines. Scan for `{...}` with depth tracking.

```js
// Key exports
capJson(args)           // run cap <args> --json, return parsed object
capStartDetached(args)  // spawn detached, read temp file, return JSON
capIsRecording()        // check cap record status
capGetPrimaryScreen()   // return id of primary screen target
```

### `lib/browser.js` — Chrome launch + Playwright

Handles Chrome app-mode launch and CDP connection from WSL.

```js
// Key exports
launchChromeApp(url, opts)          // launch Chrome --app=<url> on Windows
waitForCDP(gatewayIp, port, retries) // poll /json/version with retries
connectCDP(wsUrl)                   // chromium.connectOverCDP with retry
getGatewayIp()                      // ip route show | grep default
dismissOverlays(page)               // remove banners/cookie prompts via JS
maximizeWindow(page)                // Browser.setWindowBounds via CDP
```

**Windows-native alternative:** a companion `record-native.ps1` / `record-native.mjs`
that runs on Windows and is invoked from WSL via `powershell.exe -File ...`.
This is the reliable path for production use; CDP-from-WSL remains as fallback
for quick/one-off use.

### `lib/config.js` — Project config builder

Builds and writes `project-config.json` without opening Cap Studio.

```js
// Key exports
readConfig(projectPath)             // cap project config get --json
writeConfig(projectPath, config)    // cap project config set --settings-json
buildConfig(opts)                   // construct config from high-level options
  // opts: { background, cursor, zoom, captions, keyboard, motionBlur, spring }
```

High-level option presets:
```js
buildConfig({ preset: 'demo' })     // wallpaper bg, 10px padding, shadow, mellow cursor
buildConfig({ preset: 'clean' })    // no bg, no camera, crisp cursor
buildConfig({ preset: 'raw' })      // minimal, full-bleed, no effects
```

### `lib/zoom.js` — Zoom segment generation

Generates `zoomSegments` from Playwright event timestamps.

```js
// Usage pattern
const tracker = createEventTracker();   // attach to Playwright page
// ... drive UI, tracker records timestamps ...
const segments = tracker.toZoomSegments({
  amount: 2.0,
  preSeconds: 0.5,    // zoom in 0.5s before event
  holdSeconds: 2.5,   // stay zoomed for 2.5s after
  minGapSeconds: 1.0  // merge segments closer than 1s
});
```

```js
// Event tracker — attach to page
page.on('click', e => tracker.record('click', elapsed()));
page.on('framenavigated', () => tracker.record('nav', elapsed()));
// custom events
tracker.mark('load-complete', elapsed());
```

### `lib/preflight.js` — Gate checks

```js
// Gates
G1: cap doctor --json → captureReady: true
G2: cap targets --json → at least one screen
G3: Playwright available (node_modules or system)
G4: URL reachable (HTTP check, 401/403 = OK)
G5: Output dir exists and writable
G6: (optional) Chrome CDP alive at gateway:9222
```

### `lib/assemble.js` — ffmpeg assembly

Wraps the ffmpeg concat pipeline from reference script `assemble-video.py`,
rewritten in Node.js. Takes a manifest JSON, produces a final MP4.

---

## Key design decisions

### 1. WSL-first, Windows-native for Playwright

The skill runs from WSL (where agents live). For browser automation:
- **Default/recommended:** invoke a small Windows-native Node script via
  `powershell.exe` or copy-to-Windows pattern. No CDP cross-boundary.
- **Fallback/quick use:** CDP from WSL with 5-retry pattern. Works for
  one-off use; unreliable for CI.

The skill should make both paths available and document the trade-off clearly.

### 2. Project config is written post-recording, pre-export

The workflow is:
```
record → [timing data available] → write project-config → export
```

Not pre-recording config — that would require knowing durations in advance.
Zoom segments need actual timestamps from the recording run.

### 3. Templates, not imperative config builders

For common cases, JSON templates (in `templates/`) cover 90% of needs. For
zoom segments, a simple `addZoomSegment(config, start, end, opts)` mutator.

### 4. Beat names are caller-defined

The extension has no opinion on what beats mean. A beat is just a named
recording with its own config. The caller (the script, the agent) defines the
beat sequence and what happens during each one.

### 5. `--json` everywhere, non-zero on failure

Every command outputs a final JSON object. Errors exit non-zero with an
`{"error": "..."}` object. This makes agent integration clean.

---

## Implementation phases

### Phase 1 — Core wrappers (unblock current use)
- `lib/cap.js` — robust JSON parsing, detach spawn, status check
- `lib/config.js` — read/write project config
- `lib/zoom.js` — zoom segment builder (no Playwright yet, just the builder)
- Updated `SKILL.md` documenting `project config get|set`

### Phase 2 — Browser automation
- `lib/browser.js` — Chrome launch, CDP connect with retry, overlay dismissal
- `record-native.mjs` — Windows-native Playwright driver (no CDP)
- `lib/preflight.js` — gate checks

### Phase 3 — Beat orchestration
- `bin/cap-ext beat` — full beat record+polish+export in one command
- Event timestamp tracking integrated into browser driver

### Phase 4 — Assembly
- `lib/assemble.js` — ffmpeg pipeline (port of `assemble-video.py`)
- `bin/cap-ext assemble` — manifest-driven final video

### Phase 5 — Polish
- Templates directory with clean/demo/raw presets
- Shell completions
- Updated SKILL.md with full command reference

---

## Open questions

1. **Windows-native invocation:** best mechanism for invoking Windows Node from
   WSL? Options: `powershell.exe -File`, `cmd.exe /c`, writing a `.bat` shim,
   or using `wsl.exe` from Windows side (inverted). The `powershell.exe -File`
   path is cleanest.

2. **Event tracker integration:** how tightly should zoom generation couple to
   the Playwright driver? Options: (a) tracker is injected into every page
   automatically, (b) caller calls `tracker.mark()` manually, (c) post-hoc from
   rrweb/CDP events. Recommendation: (b) — explicit marks give the caller control
   over which events matter.

3. **Cap bundled wallpaper paths:** the `background.source.path` for the
   wallpaper preset uses a Windows path that includes the username. Need to
   either enumerate `AppData\Local\Cap\assets\backgrounds\` at runtime, or
   accept a user-configurable default background path.

4. **`cap record start` path flag:** the `--path` flag sets where the `.cap`
   project is saved. Using this to write beats to a predictable directory
   (e.g. `recordings/beats/<name>.cap`) avoids having to find them in the
   Cap library later.
