# Design — cap-ext CLI Extension

Architecture and build specification. This replaces the high-level sketch in
`REFACTOR-PLAN.md` with a concrete design grounded in the full inventory.

---

## The Core Insight: The Bridge

Previous approach (fragile):
```
WSL Playwright ──CDP WebSocket──► Windows Chrome
                  ↑ Windows Defender Firewall
                  ↑ resets this unpredictably
```

New approach (the bridge):
```
WSL (agent-browser --headed) ─── WSLg X11 ───► Chrome window on Windows desktop
                                                         │
                                          Cap records this window
                                          cap record --window <window-id>
```

**How it works:**
1. `agent-browser --headed open <url>` launches Linux Chrome (ELF binary, `~/.agent-browser/browsers/`) and renders it through WSLg. The Chrome window appears on the Windows desktop as a normal window.
2. `cap targets windows --json` discovers that window and returns its `id`.
3. `cap record --window <id>` records exactly that window — no desktop noise, no other apps.
4. `agent-browser` drives the UI from WSL. Cap records what appears on screen. They're fully independent processes with no shared connection.

**Result:** No CDP cross-boundary. No WebSocket. No Windows Defender Firewall issue. Two tools, two independent responsibilities, one clean recording.

---

## What We're Building: `cap-ext`

A WSL-resident CLI that orchestrates the full record → polish → export → assemble pipeline.

```
cap-ext record   <url> [opts]            # full cycle: open + all beats + stop + polish + export
cap-ext beat     <name> <url> [opts]     # record one named beat
cap-ext polish   <proj.cap> [opts]       # apply project-config: zoom, bg, cursor
cap-ext export   <proj.cap> <out.mp4>    # cap export wrapper
cap-ext assemble <manifest.json>         # ffmpeg assembly → final video
cap-ext preflight [url]                  # check all deps
cap-ext window   find [--wait]           # discover agent-browser window id
cap-ext config   <proj.cap> [opts]       # read/write project-config.json
```

---

## Stack

```
cap-cli-skill/
├── setup.sh                 # existing: puts cap on $PATH
├── agent.sh                 # existing: verification
├── bin/
│   └── cap-ext              # main entry (Node.js, CommonJS, no transpile needed)
├── lib/
│   ├── cap.js               # cap CLI wrapper (detach, JSON parse, retry)
│   ├── browser.js           # agent-browser wrapper (headed launch, window wait, timestamps)
│   ├── config.js            # project-config.json builder + writer
│   ├── zoom.js              # zoom segment builder from event timestamps
│   ├── preflight.js         # gate checks (G1–G6)
│   ├── export.js            # cap export wrapper with progress
│   └── assemble.js          # ffmpeg manifest pipeline (port of assemble-video.py)
├── templates/
│   ├── config-clean.json    # no bg, no camera, crisp — for terminal/code recordings
│   ├── config-demo.json     # wallpaper bg, padding, shadow, mellow cursor
│   └── manifest.example.json
└── docs/                    # this directory
```

---

## Module Design

### `lib/cap.js`

Handles all `cap-cli.exe` interactions with two reliability fixes baked in:

**Fix 1 — Detached spawn:** `cap record start --detach` is spawned to a temp
file (not `execSync`). After 2.5s, the file is read and parsed for `{recordingId}`.

**Fix 2 — JSON parsing:** Output may be multi-line pretty-printed or prefixed
with log lines. Parse with depth-tracking: scan for `{`/`[` and accumulate
until brace depth returns to zero.

```js
// Key exports
capJson(args)                    // run cap <args> --json → parsed object
capStartDetached(args)           // spawn detached → read temp file → {recordingId, pid}
capIsRecording()                 // cap record status → boolean
capGetPrimaryScreen()            // first primary screen id from cap targets
capGetWindows()                  // cap targets windows → array (may be empty)
capWaitForWindow(titleHint, ms)  // poll cap targets windows until match appears
capProjectConfigGet(path)        // cap project config get
capProjectConfigSet(path, json)  // cap project config set
```

### `lib/browser.js`

Wraps `agent-browser` (not Playwright, not raw CDP). agent-browser handles
its own Chrome session management. This module adds:

1. **Headed launch** — always uses `AGENT_BROWSER_HEADED=1` + `--color-scheme dark` for recordings.
2. **Window discovery** — after open, polls `cap targets windows` until the WSLg Chrome window appears, returns its id.
3. **Event timestamp tracking** — wraps agent-browser commands and records `{event, elapsed_ms}` from the start of recording. These become zoom segment inputs.
4. **Overlay dismissal** — injects JS via `agent-browser eval` to remove banners/cookies.

```js
// Key exports
abOpen(url, opts)               // agent-browser --headed open <url>
abClose()                       // agent-browser close
abRun(args)                     // agent-browser <args> → stdout
abEval(js)                      // agent-browser eval --stdin (heredoc-safe)
abGetCdpUrl()                   // agent-browser get cdp-url → ws://...GUID...
abStartDebugRecord(path)        // agent-browser record start <path.webm>
abStopDebugRecord()             // agent-browser record stop
abDismissOverlays()             // eval JS to remove banners
waitForWindow(titleHint, ms)    // poll cap targets windows until Chrome appears
createTracker(recordingStart)   // returns tracker.mark(label) + tracker.toTimestamps()
```

### `lib/config.js`

Builds and writes `project-config.json` without opening Cap Desktop Studio.

```js
// Key exports
readConfig(projectPath)         // cap project config get --json → object
writeConfig(projectPath, cfg)   // cap project config set --settings-json
buildConfig(opts)               // construct config from high-level options

// opts shape:
{
  preset: 'demo' | 'clean' | 'raw',  // template base
  zoomSegments: [...],                // from zoom.js
  background: { type, path, padding, rounding, shadow },
  cursor: { size, animationStyle, motionBlur },
  spring: 'snappy' | 'smooth',
  captions: true | false | { settings },
  keyboard: true | false,
  trimEnd: 120.5,                     // seconds (sets timeline.segments[0].end)
}
```

**Presets:**

| Preset | Background | Padding | Rounding | Shadow | Cursor | Spring |
|---|---|---|---|---|---|---|
| `demo` | wallpaper (sf.jpg) | 10 | 7.5 | 73.6 | mellow, 0.5 blur | snappy |
| `clean` | black solid | 0 | 0 | 0 | show, no blur | snappy |
| `raw` | none (transparent) | 0 | 0 | 0 | hide | snappy |

### `lib/zoom.js`

Generates `timeline.zoomSegments` from event timestamps collected during
the agent-browser automation run.

```js
// Usage
const tracker = createTracker();
// ... drive beat, call tracker.mark() at significant events ...
const segments = buildZoomSegments(tracker.events(), {
  amount: 2.0,
  preSeconds: 0.5,         // zoom in 0.5s before event
  holdSeconds: 2.5,        // stay zoomed 2.5s after
  minGapSeconds: 1.0,      // merge segments closer than 1s
  mode: 'auto',
  instantAnimation: false,
});
```

The tracker records `{label, elapsed_ms}` relative to when recording started.
Elapsed is computed as `Date.now() - recordingStartedAt`.

```js
// Tracker API
tracker.mark(label)              // record an event at now()
tracker.events()                 // → [{label, elapsed_s}]

// Beat integration pattern
const rec = await capStartDetached([...]);
const tracker = createTracker(Date.now());

await abOpen(url);
await waitForPage(url);
tracker.mark('page-load');

await abClick('@e1');
tracker.mark('cta-click');

await abWait('--text', 'Result');
tracker.mark('result-visible');

// Build zoom from events
const zoomSegs = buildZoomSegments(tracker.events());
```

### `lib/preflight.js`

Six gates. Any failure exits non-zero with a clear error.

```
G1  cap doctor --json           → ok: true, captureReady: true
G2  cap targets --json          → at least one screen
G3  agent-browser --version     → installed and runnable
G4  URL HTTP check              → 200/301/302 OK; 401/403 = reachable
G5  output dir writable         → mkdir -p + write test
G6  (optional) agent-browser open <url> → get url succeeds
```

### `lib/assemble.js`

Port of `assemble-video.py` to Node.js. Manifest-driven ffmpeg pipeline.

```js
// Manifest shape (identical to Python version)
{
  output_resolution: [1920, 1080],
  output_fps: 60,
  output: "output/final.mp4",
  segments: [
    { type: "camera", video: "camera/open.mp4" },
    { type: "screen", video: "beats/load.mp4",
      audio: "vo/load.wav",
      caption: "I give it the part, the material, and the room." },
    ...
    { type: "camera", video: "camera/close.mp4" }
  ]
}
```

---

## The Beat Cycle (full detail)

```
cap-ext beat "load" --url https://your-app.com --script beats/load.js
```

Internally:

```
1. PREFLIGHT
   cap doctor --json          → captureReady
   cap targets --json         → screens available
   agent-browser --version    → installed

2. OPEN BROWSER
   AGENT_BROWSER_HEADED=1 agent-browser open <url>
   agent-browser wait --load networkidle
   agent-browser set viewport 1707 1067
   agent-browser --color-scheme dark

3. WAIT FOR WINDOW
   poll cap targets windows --json every 500ms
   wait until window matching "Chrome" appears
   window_id = match.id

4. START RECORDINGS (both simultaneously)
   cap record start
     --window <window_id>
     --path beats/load.cap
     --fps 60
     --detach --json
   → recordingId (recorded)
   → recordingStartedAt = Date.now()

   agent-browser record start ./beats/load.debug.webm

5. RUN BEAT SCRIPT
   node beats/load.js
   (internally: agent-browser commands + tracker.mark() calls)
   → returns: [{label, elapsed_s}]

6. STOP RECORDINGS
   cap record stop --id <recordingId> --json
   → .cap project written to beats/load.cap
   agent-browser record stop
   → beats/load.debug.webm written

7. POLISH
   zoomSegs = buildZoomSegments(events)
   cfg = buildConfig({ preset: 'demo', zoomSegments: zoomSegs })
   cap project config set beats/load.cap --settings-json <cfg>

8. EXPORT
   cap export beats/load.cap beats/load.mp4
     --fps 60 --quality maximum --json

9. CLOSE
   agent-browser close
```

---

## The Two-Take Pattern

Every beat produces two outputs simultaneously:

| Output | Tool | Format | Purpose |
|---|---|---|---|
| `beats/<name>.cap` | Cap | `.cap` project | Polished publishable recording |
| `beats/<name>.debug.webm` | agent-browser | `.webm` | Quick debug preview, CI artifact |

The `.webm` is available immediately after the run for quick review. The `.cap` goes through polish (zoom config injection) before export.

---

## Beat Script Format

A beat script is a Node.js CommonJS module that receives an `abrowser` helper
and a tracker, executes agent-browser commands, and returns the event list.

```js
// beats/load.js
module.exports = async function beatLoad(ab, tracker) {
  // ab: thin shell wrapper for agent-browser commands
  // tracker: .mark(label) records timestamp relative to recording start

  await ab('wait --load networkidle');
  await ab('wait --text "LOAD"');
  tracker.mark('page-ready');

  await ab('find text "LOAD" click');
  tracker.mark('load-tab-click');

  await ab('wait 500');
  await ab('find text "Quick Load" click');
  tracker.mark('quick-load-click');

  await ab('wait 1500');
  tracker.mark('model-loaded');
};
```

The beat script has no knowledge of Cap, recording IDs, or file paths — it
only drives the browser and marks events.

---

## Window Discovery Flow

When `agent-browser --headed open <url>` runs:
1. WSLg renders Chrome as a Windows window
2. The window appears in `cap targets windows` within ~1-2s
3. We poll until it appears, then capture its `id`

```js
// Wait up to 10s for the window to appear
async function waitForWindow(titleHint = 'Chrome', timeoutMs = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const targets = capJson(['targets', '--json']);
    const windows = targets?.windows || [];
    const match = windows.find(w =>
      w.title?.includes(titleHint) || w.name?.includes(titleHint)
    );
    if (match) return match.id;
    await sleep(500);
  }
  throw new Error(`No window matching "${titleHint}" appeared within ${timeoutMs}ms`);
}
```

If `cap targets windows` returns `[]` (no windows open), this means either
WSLg hasn't rendered the window yet (wait longer) or the window title doesn't
match. As a fallback, use `cap record --screen <primary-id>` instead.

---

## Configuration Model

A project can have a `.cap-ext.json` at its root to configure defaults:

```json
{
  "url": "https://your-app.com",
  "outputDir": "recordings",
  "preset": "demo",
  "fps": 60,
  "resolution": [1707, 1067],
  "background": {
    "wallpaperPath": "C:\\Users\\kyleb\\AppData\\Local\\Cap\\assets\\backgrounds\\cities\\sf.jpg"
  },
  "beats": {
    "load": { "script": "beats/load.js", "pauseAfterMs": 1000 },
    "slice": { "script": "beats/slice.js" },
    "print": { "script": "beats/print.js" }
  },
  "manifest": "recordings/manifest.json"
}
```

The `wallpaperPath` needs Windows path resolution (bundled wallpapers under
`AppData\Local\Cap\assets\backgrounds\`). Enumerate at runtime or accept as
config — see REFACTOR-PLAN.md open question #3.

---

## agent-browser vs Playwright — Decision

| Scenario | Use |
|---|---|
| Driving browser for recording | `agent-browser` — lighter, WSL-native, no CDP cross-boundary issue |
| Connecting to Windows Chrome (fallback) | `agent-browser connect <ws-url>` or `--cdp <port>` |
| Complex accessibility / form interactions | `agent-browser snapshot -i` + `@refs` is sufficient for most cases |
| Playwright-specific features needed | Fall through to raw Playwright with the CDP URL from `agent-browser get cdp-url` |

The previous approach (raw `chromium.connectOverCDP` from Playwright) is
relegated to the fallback path. `agent-browser` handles the common case with
less setup, better error messages, and no CDP-from-WSL fragility.

---

## Build Phases

### Phase 1 — Core (unblock current recording use)
- `lib/cap.js` — detach spawn, JSON parsing, status check, window wait
- `lib/browser.js` — headed open, window discovery, eval overlay dismissal, tracker
- `lib/config.js` — config builder with presets
- `lib/zoom.js` — zoom segment builder
- `bin/cap-ext beat` — full beat cycle

### Phase 2 — Polish & Export
- `lib/preflight.js` — G1–G6 gates
- `lib/export.js` — progress-streaming export wrapper
- `bin/cap-ext preflight` + `cap-ext export`

### Phase 3 — Assembly
- `lib/assemble.js` — ffmpeg pipeline (port from Python)
- `bin/cap-ext assemble`
- `templates/manifest.example.json`

### Phase 4 — Config & DX
- `bin/cap-ext config` — read/write project-config.json directly
- `.cap-ext.json` project config file support
- Beat script runner with hot-reload for development
- `bin/cap-ext window find [--wait]` — standalone window discovery

---

## Open Questions (carried from REFACTOR-PLAN.md)

1. **Wallpaper path resolution:** bundled Cap wallpapers use the Windows username
   in their path. Enumerate `AppData\Local\Cap\assets\backgrounds\` at runtime
   via a Windows path call from WSL, or accept user-configured path in `.cap-ext.json`.

2. **WSLg window title:** when `agent-browser --headed` opens Chrome, what does
   the window title look like in `cap targets windows`? Needs a live test to
   confirm the `titleHint` for `waitForWindow()`.

3. **`cap record --window` vs `--screen` fallback:** if the WSLg window doesn't
   appear in `cap targets windows` (e.g., WSLg rendering delay, Cap version
   incompatibility), fall back to `--screen <primary>` automatically.

4. **agent-browser headed in WSL — does it require WSLg?** WSLg is the default
   on modern Windows 11. On older WSL2 setups, an explicit X server (VcXsrv,
   Xming) may be needed. The current env has `DISPLAY=:0` confirmed working.
