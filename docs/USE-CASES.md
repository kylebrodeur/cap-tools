# Use Cases

Generalised patterns for browser-driven screen recording with Cap. These are
use-case patterns, not project recipes.

---

## UC-1: Demo recording — scripted walkthrough of a web app

**The pattern:** Launch a browser in app/PWA mode (chromeless window). Drive it
with Playwright through a scripted set of interactions. Cap records the screen.
Stop Cap when done.

**Core loop:**
```
1. Start Cap recording (detach, capture recordingId)
2. Launch Chrome --app=<url> (chromeless, no browser UI)
3. Connect Playwright
4. Drive UI interactions
5. Stop Cap recording
6. (optional) Apply project-config: zoom, background, cursor
7. Export .cap → MP4
```

**Key decisions:**
- Drive from **Windows native Playwright** (not CDP from WSL) for reliability
- Use `--app` mode for chromeless window; no tabs, URL bar, or browser controls
- Record at 60fps for smooth playback

**Variants:**
- Full walkthrough in one recording
- Beat-based: one recording per logical segment (see UC-2)

---

## UC-2: Beat-based recording — one `.cap` project per segment

**The pattern:** A "beat" is a named, logical segment of a demo (e.g. "load",
"slice", "print"). Each beat is recorded independently: start Cap → drive one
segment → stop Cap. Each segment becomes its own `.cap` project with clean in/out
points and its own project config.

**Why beats:**
- Re-record one segment without redoing the full take
- Apply different zoom/background settings per beat
- Assemble beats into a final video in any order
- Shorter takes = less wasted effort on long flaky sequences

**Beat loop:**
```
For each beat:
  1. cap record start --screen <id> --fps 60 --detach --json → recordingId
  2. Drive the beat (Playwright)
  3. cap record stop --id <recordingId>
  4. cap project config set <beat.cap> --settings-json '<config>'
  5. cap export <beat.cap> <beat.mp4> --fps 60 --quality maximum
```

---

## UC-3: Programmatic polish — zoom/background/cursor without Studio

**The pattern:** After recording, apply all polish (auto-zoom, background
framing, cursor animation) by writing `project-config.json` via
`cap project config set`. No Cap Desktop Studio session needed.

**Why this matters:**
- Fully scriptable: agents can apply polish without a display
- Zoom segments can be generated from Playwright event timestamps
- Background/cursor are one config write, not a manual Studio session

**Zoom from event timestamps:**
```js
// Record click timestamps during Playwright automation
const events = [];
page.on('framenavigated', () => events.push({type: 'nav', t: elapsed()}));
// ... drive UI, append events ...

// After recording, build zoom segments from significant events
const zoomSegments = events
  .filter(e => e.type === 'click' || e.type === 'nav')
  .map(e => ({
    start: Math.max(0, e.t - 0.5),
    end: e.t + 2.5,
    amount: 2.0,
    mode: "auto",
    glideDirection: "none",
    glideSpeed: 0.5,
    instantAnimation: false,
    edgeSnapRatio: 0.25
  }));

// Write to project config
cap project config set recording.cap --settings-json JSON.stringify({...baseConfig, timeline: {...timeline, zoomSegments}})
```

---

## UC-4: Recording preflight — verify all deps before a take

**The pattern:** Before starting a take, run a set of gates that verify
everything is ready. Exit early with a clear error if any gate fails.

**Gates:**
1. `cap doctor --json` — cap-cli found, capture permissions OK
2. `cap targets --json` — at least one screen target available
3. Playwright reachable (Node installed, `playwright` package present)
4. Target URL responds (HTTP check, handle 401/403 as "reachable")
5. Output directory exists and is writable
6. (optional) Verify Chrome CDP is alive if using CDP mode

**Implementation:** a small script (Node or Python) that runs all gates and
prints `✓ / ✗` per gate, exits non-zero on failure. Can be run as
`make record-check` or similar.

---

## UC-5: Export pipeline — `.cap` → MP4

**The pattern:** Export a `.cap` project to MP4 with specific resolution, fps,
and quality settings.

```bash
cap export recording.cap output.mp4 \
  --resolution 1920x1080 \
  --fps 60 \
  --quality maximum \
  --json
```

**Formats:** `mp4` (default), `gif`, `mov`
**Quality presets:** `maximum`, `social`, `web`, `potato`

**Progress:** `cap export` emits NDJSON progress events:
```json
{"type": "Progress", "rendered_count": 42, "total_frames": 360}
{"type": "Completed", "path": "/path/to/output.mp4"}
```

**Export settings as JSON** (alternative to flags):
```bash
cap export recording.cap output.mp4 \
  --settings-json '{"format":"Mp4","fps":60,"resolution_base":{"x":1920,"y":1080},"compression":"Maximum"}'
```

---

## UC-6: Video assembly — multiple clips → final video

**The pattern:** Assemble exported beat clips + camera footage + voice-over
audio into a final video using ffmpeg. A manifest JSON describes the segments
in story order.

**Manifest format:**
```json
{
  "output_resolution": [1920, 1080],
  "output_fps": 60,
  "output": "output/final.mp4",
  "segments": [
    {"type": "camera", "video": "camera/open.mp4"},
    {"type": "screen", "video": "beats/load.mp4", "audio": "vo/load.wav",
     "caption": "I give it the part, the material, and the room."},
    {"type": "screen", "video": "beats/demo.mp4"},
    {"type": "camera", "video": "camera/close.mp4"}
  ]
}
```

**Assembly pipeline (ffmpeg):**
1. For each segment: scale/pad to output resolution, mix audio (VO or original), burn captions
2. Concat all segments via `ffmpeg -f concat`

---

## UC-7: Screenshot capture for visual verification

**The pattern:** Take a still screenshot of a screen or window to verify the
UI state before/after a recording, or as a lightweight alternative to a full
recording for CI checks.

```bash
cap screenshot --screen <id> --output /tmp/verify.png --json
```

Returns `{path, width, height}`. Useful for:
- Pre-recording state verification
- Post-action confirmation (did the UI update?)
- Generating thumbnails for recording library

---

## UC-8: CDP `Page.startScreencast` for live pixel streaming

**The pattern:** For live "watch the agent work" views (not recordings), use
CDP's `Page.startScreencast` to stream frames from a browser page in real time.

```js
const client = await page.context().newCDPSession(page);
await client.send('Page.startScreencast', {
  format: 'jpeg',
  quality: 80,
  maxWidth: 1280,
  maxHeight: 800,
  everyNthFrame: 1
});
client.on('Page.screencastFrame', ({data, sessionId}) => {
  // data is base64 JPEG — stream to WebSocket / display
  client.send('Page.screencastFrameAck', {sessionId});
});
```

This is distinct from Cap screen recording (which captures the full OS desktop).
Use `startScreencast` for real-time monitoring/streaming; use Cap for the final
pixel-perfect recording artifact.

---

## UC-9: Windows-native Playwright for reliable browser automation from WSL

**The pattern:** When WSL needs to automate a browser on Windows reliably,
run Playwright natively on Windows (Node on Windows, no CDP cross-boundary).

**Setup:**
1. Install Node on Windows
2. Copy/sync the Playwright project to a Windows path (e.g. `C:\project-e2e`)
3. Run `npx playwright test` from Windows PowerShell / cmd

**Invoking from WSL:**
```bash
powershell.exe -Command "cd C:\project-e2e; npx playwright test"
# or
cmd.exe /c "cd /d C:\project-e2e && npx playwright test"
```

**Why:** CDP-from-WSL fails unpredictably due to Windows Defender Firewall
resetting WebSocket connections (see FINDINGS.md §7). Native Windows avoids
the cross-boundary WebSocket entirely.

---

## UC-11: Terminal / multi-pane demo recording

**The pattern:** When the demo surface is a terminal (Pi agent, TUI, Zellij layout) rather
than a browser, Cap records the full OS screen — terminal included. The same
beat-based workflow applies: one `.cap` project per logical segment.

**Source:** `pi-tools/docs/demo-architecture-patterns.md`

Key pre-recording checklist (generalised from the pattern):
- Clean state: wipe any local data/ledger dirs so the demo starts fresh
- Verify all background services are up before starting Cap
- Test-record a 30s clip to confirm font size is legible at video resolution
- Have a script for what you'll type — don't freestyle commands on camera
- Screen layout clean: close unrelated windows, hide notifications

**Three-terminal topology for complex demos:**
- **Terminal A** (the recording target): the primary interaction surface. Keep
  output here clean and sequential.
- **Terminal B** (ambient view): live-updating dashboard. Uses in-place ANSI
  redraws (`\x1b[2J\x1b[H`) for a live feel.
- **Terminal C** (optional): overflow context, reasoning traces.

The same Cap beat-per-segment approach works: record Terminal A alone,
or record all three panes via a Zellij/tmux layout in a single Cap take.

---

## UC-12: `agent-browser` WebM recording (in-browser capture, not OS screen)

**The pattern:** `agent-browser` (a CDP-based browser automation CLI) has its
own built-in recording that captures the browser tab directly to WebM:

```bash
agent-browser record start ./demo.webm
agent-browser open https://example.com
agent-browser snapshot -i
agent-browser click @e1
agent-browser record stop
```

**Source:** `claude-knowledge-explorer/.agents/skills/agent-browser/references/video-recording.md`

**How this differs from Cap:**

| | Cap screen recording | `agent-browser record` |
|---|---|---|
| **What it captures** | Full OS screen (any app) | Browser tab only |
| **Output format** | `.cap` project → MP4/GIF/MOV | `.webm` directly |
| **Polish** | `project-config.json` — zoom, bg, cursor | None (raw capture) |
| **Best for** | Polished demo videos | Quick debugging, CI artifacts |
| **Requires** | Cap Desktop installed | `agent-browser` installed |

**`agent-browser get cdp-url`** returns the CDP WebSocket URL for the current
session. This is useful when you want a _second_ tool (Cap, or a custom
recorder) to connect to the same browser that `agent-browser` is already
driving — bridging the two approaches.

**`agent-browser stream enable`** starts a WebSocket frame stream on an
auto-selected port. This enables live pixel monitoring of what the browser
is doing — a lighter alternative to Cap's full-screen recording when you
only need to observe browser state, not produce a polished artifact.

---

## UC-13: Hackathon / submission demo recording (multi-project pattern)

**The pattern:** A recurring need across multiple projects (an internal project,
spanish-tutor, audio-transcription, brain-tree-os) is producing a 2-5 minute
demo video for a hackathon or product launch. Each time this is solved
ad-hoc with OBS/QuickTime or CapCut.

**Sources:** `an internal project/docs/_archive/hackathon-sprint/05-VIDEO.md`,
`_backlog/spanish-tutor-platform/.agent/plans/NEEDS_REVIEW-Post-Deploy-Demo-Plan.md`,
`audio-transcription/docs/_archive/DEPLOYMENT_QUICKSTART.md`

**Common structure across all projects:**
1. **Open** — camera, personal story, ~20-30s
2. **Demo beats** — scripted screen recording, one section per feature
3. **Close** — back to camera, call to action, ~15s

**The repeated pain point:** Each project reinvents the recording setup,
the segment structure, and the assembly. The cap-cli extension's beat-based
workflow directly addresses this. A generalised `cap-ext` command covering
preflight + per-beat recording + assembly would have been reusable across
all of them.

---

## UC-10: Upload and share

```bash
# Upload a .cap project (requires Cap Desktop login or CAP_API_KEY)
cap upload recording.cap --json
# → {"url": "https://cap.so/s/abc123", ...}

# Upload an MP4
cap upload output.mp4 --json
```

Set `CAP_API_KEY` env var for headless/CI (get from Cap Settings). Without it,
`cap upload` reuses the login stored by Cap Desktop.
