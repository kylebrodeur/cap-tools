# Architecture — cap-ext CLI Extension

Design decisions, workflow, code-level module breakdown, and build phases.

---

## The Core Decision: Browser runs on Windows, not WSL

**Rule: never open the browser from WSL.** The browser must run on the
Windows host side. This is exactly what a companion project proved works: copy the
project to Windows, run it natively via PowerShell. WSL orchestrates;
Windows executes.

### Why

Windows Defender Firewall resets WebSocket connections that cross the
WSL→Windows boundary. CDP from WSL works sometimes (HTTP probes succeed)
but fails non-deterministically at the WebSocket upgrade layer. The fix
is to avoid the cross-boundary WebSocket entirely.

### The bridge

```
WSL (orchestration) ──powershell.exe──► Windows (browser + Cap)
                                              │
                          Playwright launches Chrome natively
                          Cap records the screen/window
```

WSL invokes a Windows-side Node.js script via `powershell.exe -Command`.
That script launches Chrome natively on Windows (Playwright, no CDP),
starts/stops Cap recording, drives the UI, collects event timestamps,
and writes results to a shared file. WSL reads the results, applies
polish (project-config), exports, and assembles.

### Paths evaluated

| Path | Browser on | CDP boundary | Verdict |
|---|---|---|---|
| CDP from WSL | Windows | ✗ Firewall resets WS | ❌ Fragile |
| WSLg (Linux Chrome) | WSL | ✓ none | ❌ Browser on wrong side |
| **Windows-native** | Windows | ✓ none | ✅ Correct |

---

## Command Surface

```
cap-ext record   <url> [opts]            # full cycle: all beats + polish + export
cap-ext beat     <name> <url> [opts]     # record one named beat
cap-ext polish   <proj.cap> [opts]       # apply project-config: zoom, bg, cursor
cap-ext export   <proj.cap> <out.mp4>    # cap export wrapper
cap-ext assemble <manifest.json>         # ffmpeg assembly → final video
cap-ext preflight [url]                  # check all deps
cap-ext config   <proj.cap> [opts]       # read/write project-config.json
```

---

## The Beat Cycle

```
cap-ext beat "load" --url http://wsl.localhost:7860
```

1. **Preflight (WSL)** — cap doctor, cap targets, PowerShell reachable, URL check
2. **Invoke Windows beat-runner (WSL → Windows)** — `powershell.exe -Command "cd C:\cap-ext; node beat-runner.js load http://wsl.localhost:7860 C:\recordings"`
3. **Beat-runner executes (Windows)** — launch Chrome natively, start Cap, drive beat, collect timestamps, stop Cap, write results JSON
4. **Read results (WSL)** — parse `/mnt/c/recordings/load.json` → `{recordingId, capProjectPath, events}`
5. **Polish (WSL)** — build zoom segments from events, write project-config
6. **Export (WSL)** — `cap export` → MP4

---

## The Two-Take Pattern

Every beat produces two outputs simultaneously:

| Output | Tool | Format | Purpose |
|---|---|---|---|
| `beats/<name>.cap` | Cap | `.cap` project | Polished publishable recording |
| `beats/<name>.debug.webm` | Playwright | `.webm` | Quick debug preview |

The `.webm` is captured by Playwright's built-in video recording during the
beat run. The `.cap` goes through polish (zoom config injection) before export.

---

## Beat Definitions

Beats are defined as JSON step sequences. The beat-runner on Windows loads
them from a shared config file.

```json
{
  "load": {
    "steps": [
      { "action": "goto", "url": "http://wsl.localhost:7860" },
      { "action": "wait", "selector": "button:has-text('LOAD')" },
      { "action": "mark", "label": "page-ready" },
      { "action": "click", "selector": "button:has-text('LOAD')" },
      { "action": "mark", "label": "load-tab-click" },
      { "action": "wait", "ms": 500 },
      { "action": "click", "selector": "#quick-load" },
      { "action": "mark", "label": "quick-load-click" },
      { "action": "wait", "ms": 1500 },
      { "action": "mark", "label": "model-loaded" }
    ]
  }
}
```

The `mark` action records a timestamp relative to recording start. These
become zoom segment inputs during the polish phase.

---

## Configuration Model

A project can have a `.cap-ext.json` at its root:

```json
{
  "url": "http://wsl.localhost:7860",
  "outputDir": "recordings",
  "windowsOutputDir": "C:\\recordings",
  "preset": "demo",
  "fps": 60,
  "resolution": [1707, 1067],
  "screenId": "199517",
  "beats": {
    "load": { "steps": [...], "pauseAfterMs": 1000 }
  },
  "manifest": "recordings/manifest.json"
}
```

---

## Windows Setup (one-time)

```powershell
mkdir C:\cap-ext
Copy-Item -Recurse \\wsl.localhost\<repo>\win\* C:\cap-ext\
cd C:\cap-ext
npm install
npx playwright install chromium
```

Verify:
```powershell
node beat-runner.js --check
```

---

## Open Questions

1. **Wallpaper path resolution:** bundled Cap wallpapers use the Windows
   username in their path. Enumerate at runtime or accept in config.

2. **Shared file path:** WSL reads Windows files at `/mnt/c/...`. The
   beat-runner writes to `C:\recordings\`; WSL reads from `/mnt/c/recordings/`.
   This is the same pattern a companion project used — it works.

3. **`wsl.localhost` for the target URL:** `wsl.localhost` does NOT resolve
   in Windows Playwright (confirmed by a companion project §11). The beat-runner on
   Windows must use `http://127.0.0.1:<port>` (if netsh portproxy is set up)
   or the WSL IP directly. For WSL-hosted apps, set up a one-time netsh
   portproxy rule per port.

4. **Tailscale for HTTPS:** only needed when the target app requires HTTPS
   (WordPress with HTTPS constants, Secure cookies, HSTS). For plain HTTP
   apps, `wsl.localhost` is sufficient.

---

## Stack Layout

```
cap-cli-skill/
├── setup.sh                 # existing: puts cap on $PATH
├── agent.sh                 # existing: verification
├── bin/
│   └── cap-ext              # main entry (Node.js, CommonJS, WSL-side)
├── lib/                     # WSL-side modules
│   ├── cap.js               # cap CLI wrapper (detach, JSON parse, retry)
│   ├── config.js            # project-config.json builder + writer
│   ├── zoom.js              # zoom segment builder from event timestamps
│   ├── preflight.js         # gate checks (G1–G6)
│   ├── export.js            # cap export wrapper with progress
│   └── assemble.js          # ffmpeg manifest pipeline (port of assemble-video.py)
├── win/                     # Windows-side — copied to C:\cap-ext\ on setup
│   ├── beat-runner.js       # Node.js: starts Cap, drives Playwright, stops Cap
│   ├── package.json         # deps: playwright
│   └── install.ps1          # one-time: npm install + playwright install chromium
├── templates/
│   ├── config-clean.json    # no bg, no camera, crisp
│   ├── config-demo.json     # wallpaper bg, padding, shadow, mellow cursor
│   └── manifest.example.json
└── docs/
```

---

## WSL-side Modules

### `lib/cap.js`

Handles all `cap-cli.exe` interactions. Cap is a Windows binary — it runs
from WSL via the `cap()` shell function in `setup.sh`.

Two reliability fixes baked in:

**Fix 1 — Detached spawn:** `cap record start --detach` is spawned to a temp
file (not `execSync`). After 2.5s, the file is read and parsed for
`{recordingId}`.

**Fix 2 — JSON parsing:** Output may be multi-line pretty-printed or prefixed
with log lines. Parse with depth-tracking: scan for `{`/`[` and accumulate
until brace depth returns to zero.

```js
capJson(args)                    // run cap <args> --json → parsed object
capStartDetached(args)           // spawn detached → read temp file → {recordingId, pid}
capIsRecording()                 // cap record status → boolean
capGetPrimaryScreen()            // first primary screen id from cap targets
capProjectConfigGet(path)        // cap project config get
capProjectConfigSet(path, json)  // cap project config set
```

### `lib/config.js`

Builds and writes `project-config.json` without opening Cap Desktop Studio.

```js
readConfig(projectPath)         // cap project config get --json → object
writeConfig(projectPath, cfg)   // cap project config set --settings-json
buildConfig(opts)               // construct config from high-level options

// opts shape:
{
  preset: 'demo' | 'clean' | 'raw',
  zoomSegments: [...],
  background: { type, path, padding, rounding, shadow },
  cursor: { size, animationStyle, motionBlur },
  spring: 'snappy' | 'smooth',
  captions: true | false | { settings },
  keyboard: true | false,
  trimEnd: 120.5,
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
the Windows-side beat run.

```js
buildZoomSegments(events, opts)
// events: [{label, elapsed_s}, ...]
// opts: { amount, preSeconds, holdSeconds, minGapSeconds, mode }
// → [{start, end, amount, mode: "auto", ...}]
```

Merges overlapping segments (gap < `minGapSeconds`) into one longer zoom.

### `lib/preflight.js`

Six gates. Any failure exits non-zero with a clear error.

```
G1  cap doctor --json           → ok: true, captureReady: true
G2  cap targets --json          → at least one screen
G3  powershell.exe reachable    → powershell.exe -Command "echo ok"
G4  URL HTTP check              → 200/301/302 OK; 401/403 = reachable
G5  output dir writable         → mkdir -p + write test
G6  Windows beat-runner ready   → powershell.exe -Command "node C:\cap-ext\beat-runner.js --check"
```

### `lib/assemble.js`

Port of `assemble-video.py` to Node.js. Manifest-driven ffmpeg pipeline.

```json
{
  "output_resolution": [1920, 1080],
  "output_fps": 60,
  "output": "output/final.mp4",
  "segments": [
    { "type": "camera", "video": "camera/open.mp4" },
    { "type": "screen", "video": "beats/load.mp4",
      "audio": "vo/load.wav",
      "caption": "I give it the part, the material, and the room." },
    { "type": "camera", "video": "camera/close.mp4" }
  ]
}
```

Per-segment: scale/pad to output resolution, mix VO audio, burn captions
via `drawtext`. Two-pass: render segments to temp dir → `ffmpeg -f concat`.

---

## Windows-side Module

### `win/beat-runner.js`

The only code that runs on Windows. Invoked from WSL via PowerShell:

```powershell
powershell.exe -Command "cd C:\cap-ext; node beat-runner.js <beat-name> <url> <output-dir>"
```

Responsibilities:
1. Launch Chrome natively via Playwright (`chromium.launch({ headless: false })`)
2. Start Cap recording (`cap record start --screen <id> --fps 60 --detach --json --path <out>.cap`)
3. Drive the beat (navigate, click, wait — Playwright commands)
4. Collect event timestamps (`{label, elapsed_ms}`)
5. Stop Cap recording
6. Write results to a shared file: `{recordingId, events[], capProjectPath}`

The beat-runner has no knowledge of polish, export, or assembly — it only
records and drives.

```js
// win/beat-runner.js (runs on Windows)
const { chromium } = require('playwright');
const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const BEAT = process.argv[2];
const URL = process.argv[3];
const OUT = process.argv[4];

// 1. Launch Chrome
const browser = await chromium.launch({ headless: false });
const page = await browser.newPage();
await page.setViewportSize({ width: 1707, height: 1067 });

// 2. Start Cap
const capResult = capStartDetached([
  'record', 'start', '--screen', SCREEN_ID, '--fps', '60',
  '--detach', '--json', '--path', path.join(OUT, `${BEAT}.cap`)
]);
const recordingId = capResult.recordingId;
const startTime = Date.now();

// 3. Drive the beat
const events = [];
await page.goto(URL);
events.push({ label: 'page-load', elapsed_ms: Date.now() - startTime });
// ... beat-specific steps from beats.json ...

// 4. Stop Cap
execSync(`cap record stop --id ${recordingId}`);

// 5. Write results
fs.writeFileSync(path.join(OUT, `${BEAT}.json`), JSON.stringify({
  recordingId,
  capProjectPath: path.join(OUT, `${BEAT}.cap`),
  events,
  durationMs: Date.now() - startTime
}));

await browser.close();
```

---

## Build Phases

### Phase 1 — Core
- `lib/cap.js` — detach spawn, JSON parsing, status check
- `win/beat-runner.js` — Windows-side: Playwright + Cap + event tracking
- `lib/config.js` — config builder with presets
- `lib/zoom.js` — zoom segment builder
- `bin/cap-ext beat` — full beat cycle (WSL → PowerShell → Windows → WSL)

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
- Beat step definitions in JSON (shared between WSL and Windows)
- `win/install.ps1` — one-time Windows setup script
