# Findings

Technical findings from research across two projects. Generalised — not tied
to either source project.

**Sources**
- `an internal reference project/the source project/` — recording scripts and docs
- `a companion project/docs/_reference/SESSION-LEARNINGS-2026-06-26.md` — CDP/WSL findings
- `a companion project/docs/decisions/ADR-011-agent-ui-interaction.md` — Playwright/CDP architecture
- `a companion project/docs/decisions/ADR-012-visual-annotation-review.md` — capture strategy
- `a companion project/docs/_research/RRWEB-REPLAY-EXTRACT.md` — rrweb research
- Live `cap guide --json`, `cap export --help`, `cap project config` — CLI introspection
- Real `project-config.json` files from actual `.cap` recordings on disk

---

## 1. `project-config.json` is the Studio, programmatically

**The finding:** Cap Desktop Studio is a UI over `project-config.json`. Every
feature you'd use the Studio for — auto-zoom, background, cursor style, captions,
keyboard overlays, motion blur — lives in this JSON document and is read/written
via `cap project config get|set`.

```bash
# Read a project's config
cap project config get path/to/recording.cap --json

# Write a full config (omitted fields reset to defaults)
cap project config set path/to/recording.cap \
  --settings-json '{"background":{"source":{"type":"wallpaper","path":"..."},...},...}'
```

This means the full "record → polish → export" pipeline is scriptable without
ever opening the Desktop app. See [PROJECT-CONFIG-SCHEMA.md](./PROJECT-CONFIG-SCHEMA.md)
for the full schema.

---

## 2. Auto-zoom is `timeline.zoomSegments` — no Studio required

Auto-zoom (the feature where Cap zooms in to follow cursor activity) is stored as
an array of time-ranged segments in `project-config.json`. Each segment specifies
start/end timestamps in seconds, a zoom amount, and `mode: "auto"` to follow the
cursor automatically.

```json
"timeline": {
  "zoomSegments": [
    {
      "start": 12.5,
      "end": 18.0,
      "amount": 2.0,
      "mode": "auto",
      "glideDirection": "none",
      "glideSpeed": 0.5,
      "instantAnimation": false,
      "edgeSnapRatio": 0.25
    }
  ]
}
```

**Implication:** when driving a browser with Playwright, you know exactly when
clicks and UI events happen. Those timestamps can be recorded and used to inject
zoom segments into the project config before export — giving you polished
auto-zoom without opening Studio.

Observed values from real projects:
- `amount: 2.0` — strong zoom (demo-style, 2× magnification)
- `amount: 1.5` — subtle zoom (presentation-style)
- `mode: "auto"` — Cap tracks the cursor in the zoomed window automatically

---

## 3. Background, framing, and shadow are config fields

The "desktop background" look (recording floating on a coloured/wallpaper
background with rounded corners and a shadow) is controlled by `background.*`:

| Setting | Raw recording | Framed/demo look |
|---|---|---|
| `background.source.type` | `"color"` with white/black | `"wallpaper"` with a path |
| `background.padding` | `0.0` | `10.0` |
| `background.rounding` | `0.0` | `7.5` |
| `background.shadow` | any | `73.6` (prominent shadow) |

The `"wallpaper"` type references bundled Cap assets at
`C:\Users\<user>\AppData\Local\Cap\assets\backgrounds\`. Other types seen in
practice: `"color"` (RGBA array + alpha). Gradient and image types likely exist
but were not observed.

---

## 4. Cursor style and motion blur are config fields

No Studio needed for cursor animation, size, or motion blur:

```json
"cursor": {
  "hide": false,
  "animationStyle": "mellow",   // spring-follow style
  "size": 100,                  // 100 = standard, 200 = large
  "motionBlur": 0.5,            // 0-1; trail behind cursor
  "type": "auto",               // cursor graphic
  "hideWhenIdle": false,
  "clickSpring": null           // null = default click animation
}
```

`animationStyle: "mellow"` is the smooth spring-follow seen in demo recordings.
`motionBlur` adds a velocity-proportional blur trail.

---

## 5. Screen motion blur and zoom spring physics are config fields

The smoothness of zoom transitions is controlled by:

```json
"screenMotionBlur": 0.5,
"screenMovementSpring": {
  "stiffness": 200.0,
  "damping": 40.0,
  "mass": 2.25
}
```

Two observed presets:
- **Snappy** (demo/presentation): `stiffness: 200, damping: 40, mass: 2.25`
- **Smooth/elastic**: `stiffness: 120, damping: 14, mass: 1.0`

Set `screenMotionBlur: 0.0` for a crisp zoom with no blur.

---

## 6. Captions and keyboard overlays are config fields

Both the caption overlay and the keystroke display are programmatically
configurable. Captions can be pre-loaded with timed segments; keyboard segments
are auto-populated during recording but their display style is configurable.

```json
"captions": {
  "segments": [],
  "settings": {
    "enabled": true,
    "font": "System Sans-Serif",
    "size": 50,
    "color": "#FFFFFF",
    "backgroundColor": "#000000",
    "backgroundOpacity": 95,
    "position": "bottom-center"
  }
},
"keyboard": {
  "settings": {
    "enabled": true,
    "fadeDuration": 0.15,
    "lingerDuration": 0.8,
    "groupingThresholdMs": 500.0,
    "showModifiers": true,
    "showSpecialKeys": true
  }
}
```

Setting `captions: null` or `keyboard: null` disables the overlay entirely.

---

## 7. CDP from WSL is unreliable — use native Windows Playwright instead

**Finding from a companion project SESSION-LEARNINGS-2026-06-26:**

The standard approach of launching Chrome on Windows with
`--remote-debugging-port=9222 --remote-debugging-address=0.0.0.0` and
connecting from WSL via the gateway IP works for the HTTP probe
(`/json/version`) but fails unpredictably at the WebSocket layer:

- Windows Defender Firewall resets WebSocket connections intermittently
- The issue is non-deterministic — it works sometimes and not others
- Adding retry loops (5 attempts × 3s sleep) reduces but doesn't eliminate failures

**The fix:** run Playwright natively on Windows (Node installed on Windows,
project copied to e.g. `C:\project-e2e`). Chrome launches directly on Windows
and no cross-boundary WebSocket is needed.

```typescript
// No CDP, no connectOptions — just native Chrome launch
export default defineConfig({
  use: {
    baseURL: 'http://127.0.0.1:<port>',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
```

**When CDP from WSL is acceptable:** for short, low-stakes automations (like
driving a quick UI walk-through once) the retry pattern works well enough. For
reliable CI or repeated takes, native Windows is required.

---

## 8. CDP WebSocket URL requires the dynamic GUID — not the static port

When CDP is used from WSL, the `webSocketDebuggerUrl` returned by
`GET /json/version` contains a browser-instance GUID:

```
ws://127.0.0.1:9222/devtools/browser/abc123-def456-...
```

The hostname in this URL is always `127.0.0.1` (Chrome's own loopback). It
**must** be rewritten to the Windows gateway IP before using it from WSL:

```js
const info = await fetch(`${CDP_URL}/json/version`).then(r => r.json());
const raw = info.webSocketDebuggerUrl;           // ws://127.0.0.1:9222/devtools/browser/GUID
const u = new URL(raw);
u.hostname = gatewayIp;                          // rewrite to 172.25.x.x
u.port = '9222';
const wsUrl = u.toString();                      // ws://172.25.x.x:9222/devtools/browser/GUID
browser = await chromium.connectOverCDP(wsUrl);
```

Passing the static `http://172.25.x.x:9222` as the endpoint will fail —
Playwright needs the full `ws://` URL with the GUID path.

---

## 9. Chrome `--app` mode gives a clean chromeless window

Launching Chrome with `--app=<url>` opens it as a PWA-style window with no
address bar, tabs, or browser chrome. Ideal for screen recordings where you
want only the web app visible.

```bash
# WSL calling Windows Chrome
"C:\Program Files\Google\Chrome\Application\chrome.exe" \
  --app=https://your-app.example.com \
  --remote-debugging-port=9222 \
  --remote-debugging-address=0.0.0.0 \
  --window-size=1707,1067 \
  --window-position=0,0 \
  --user-data-dir=/tmp/chrome-record-profile \
  --disable-session-crashed-bubble \
  --no-first-run \
  --no-default-browser-check
```

The Gradio/HF Space PWA install prompt ("Install this app") creates the same
effect but persists across sessions. Either approach works.

---

## 10. `cap record start --detach --json` returns a `recordingId`

The `--detach` flag starts Cap recording in the background and immediately
returns a JSON object containing a `recordingId`. This ID is required to stop
the specific recording later:

```bash
cap record start --screen <id> --fps 60 --detach --json
# → {"type":"started","recordingId":"abc123","pid":1234,...}

cap record stop --id abc123 --json
# → {"type":"stopped","path":"abc123.cap",...}
```

**Gotcha:** Cap is non-blocking when detached. The `--json` output is written
asynchronously to stdout after the process is backgrounded. You must spawn it
to a temp file, sleep ~2.5s, then parse the file. Do not use `execSync` — it
will block forever waiting for the process to exit.

---

## 11. Cap JSON output can be multi-line and prefixed with log lines

`cap` sometimes emits log lines before the JSON object, and sometimes emits
pretty-printed multi-line JSON. A robust parser:

1. Try single-line: scan lines for one that starts with `{` and ends with `}`
2. Fall back to depth-tracking: accumulate lines from the first `{` or `[`
   until brace depth returns to zero

Do not assume `JSON.parse(output)` works directly.

---

## 12. `cap record status --json` for detecting active recordings

Before starting a new recording, check if one is already running:

```bash
cap record status --json
# → {"sessions":[{"recordingId":"abc","state":"recording",...}]}

# or from recordings list
cap recordings list --json
```

Check `state === "recording"` or `state === "in-progress"`.

---

## 13. Per-beat recording gives clean independent `.cap` projects

The pattern of starting Cap, driving one logical UI segment, stopping Cap,
then repeating for the next segment produces independent `.cap` projects — one
per beat. This gives:
- Clean in/out points per segment (no trimming needed)
- Independent project configs (different zoom, background per segment)
- Ability to re-record one segment without redoing the full take
- Easy assembly: export each beat to MP4, then concat

---

## 14. HF Space / web overlay dismissal via JS injection

When recording a Hugging Face Space (or any site with cookie banners / headers),
the overlays must be removed before or immediately after navigation to avoid
them appearing in the recording:

```js
await page.evaluate(() => {
  // HF Space header
  document.getElementById('huggingface-space-header')?.remove();
  // Cookie/consent banners (heuristic)
  document.querySelectorAll('div, aside, section').forEach(el => {
    if (/(cookie|accept|privacy)/i.test(el.innerText) && el.innerText.length < 400) {
      el.remove();
    }
  });
  // Auto-click dismiss buttons
  document.querySelectorAll('button').forEach(btn => {
    if (/^(accept|allow all|got it|agree|ok|dismiss|close)$/i.test(btn.innerText.trim())) {
      btn.click();
    }
  });
});
```

Run this in a polling loop for the first 6-8 seconds after page load, then
once more before each beat starts.

---

## 15. `Browser.setWindowBounds` via CDP for maximising

When connected to Chrome via CDP, the OS window can be maximised without
relying on PowerShell or OS-level focus calls:

```js
const cdpSession = await page.context().newCDPSession(page);
const { windowId } = await cdpSession.send('Browser.getWindowForTarget');
await cdpSession.send('Browser.setWindowBounds', {
  windowId,
  bounds: { windowState: 'maximized' }
});
```

This ensures the recording fills the screen even if the window wasn't
fullscreen when Chrome was launched.

---

## 16. rrweb is a recording format, not model input

From a companion project ADR-011/012 and RRWEB-REPLAY-EXTRACT.md:

- **rrweb / PostHog session replay** is a fine event-log format for recording
  browser sessions.
- **Never feed raw rrweb JSON to an LLM** — it is context-annihilating (5-10 MB
  for a 3-minute session), delta-not-absolute state, and Shadow DOM/Canvas-blind.
- The correct pattern: replay rrweb in headless Playwright, extract a
  **Set-of-Marks screenshot + AXTree** at the relevant moment, feed that to
  the model.
- **For human viewers** (live "watch the agent" view): native Chrome capture
  — `CDP Page.startScreencast` or `getDisplayMedia` — gives true pixels.

For recording use cases (not agent perception), rrweb stays as an optional
event log; cap's screen recording is the pixel source.

---

## 17. `agent-browser` has built-in WebM recording + CDP URL exposure

**Source:** `claude-knowledge-explorer/.agents/skills/agent-browser/`

`agent-browser` is a separate CDP-based browser automation CLI with its own
recording path:

```bash
agent-browser record start ./demo.webm   # record tab directly to WebM
agent-browser record stop

agent-browser get cdp-url               # get CDP WebSocket URL of current session
agent-browser stream enable             # start live WebSocket pixel stream
```

**The bridge opportunity:** `agent-browser get cdp-url` exposes the CDP
WebSocket URL for the browser it's already running. This means:

1. Use `agent-browser` to drive the UI (it's the simpler automation API)
2. Call `agent-browser get cdp-url` to get the live CDP endpoint
3. Pass that URL to Cap (via `record start --window`) or connect a second
   Playwright session for Cap coordination

This is a cleaner CDP story than the WSL→Windows path: `agent-browser`
runs the browser and holds the session; Cap records the OS screen; the two
are independent and don't need to share a WebSocket connection.

**`agent-browser record` vs Cap:**
- `agent-browser record` → browser-tab-only WebM, no polish, no zoom
- Cap screen recording → full OS screen, polished via `project-config.json`
- Both can run simultaneously: `agent-browser` drives the UI + records
  a quick debug take; Cap records the polished take for publishing

---

## 18. Terminal recording is the same OS-screen use case

Multiple projects (an internal project original, pi-tools demo patterns) record
terminal demos: Zellij multi-pane layouts, Pi agent sessions, ANSI
dashboards. Cap records the OS screen, so terminals are just another
target — no special handling needed.

Key generalised checklist items from `pi-tools/docs/demo-architecture-patterns.md`:
- Clean state before take (wipe ledger/data dirs)
- Test-record 30s to verify font legibility at video resolution
- Script what you'll type — no freestyle CLI commands on camera
- Three-terminal topology (control / dashboard / overflow) maps directly
  to the beat structure: record Terminal A (control) as the primary take;
  Terminal B can be a cutaway beat recorded separately or as a PiP

---

## 19. Recurring demo video need across projects — no systematic workflow

**Sources:** an internal project, spanish-tutor, audio-transcription, brain-tree-os,
mcp-network-analyzer — all needed 2-5 min demo videos for hackathon/launch.

Each solved it ad-hoc (OBS, QuickTime, CapCut). The common structure:
open (camera) → beats (screen) → close (camera) is identical across all
of them. A generalised cap-ext with beat + assemble commands would have
been reusable as-is across every one of these projects.

---

## 20. WSL2 Networking Model — Full Reference

**Source:** a companion project `SESSION-LEARNINGS-2026-06-26.md` §1 + live environment
verification. Items marked **[+]** are things the a companion project session did not
document.

### The two IP addresses (NAT mode)

`networkingMode=nat` in `.wslconfig` — WSL2 runs in a VM with its own network
namespace. Two IPs are always in play:

| Address | What it is | Direction |
|---|---|---|
| `<gateway-ip>` e.g. `172.x.x.1` | Windows host (virtual Ethernet adapter) | WSL → Windows |
| `<wsl-ip>` e.g. `172.x.x.x` | WSL instance | Windows → WSL |

Get them at runtime:
```bash
GATEWAY=$(ip route show | grep default | awk '{print $3}')   # Windows host
WSL_IP=$(ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)  # WSL
```

These are **not interchangeable.** Never use the gateway IP to reach WSL
services from Windows, or the WSL IP to reach Windows services from WSL.

### `wsl.localhost` — the stable hostname that works from both sides **[+]**

`wsl.localhost` resolves to the WSL instance from **both sides**:
- From Windows → reaches WSL services (documented by a companion project)
- **From WSL itself → also works** (confirmed via live test)

This is the correct URL for beat scripts referencing a WSL-hosted app:

```bash
agent-browser open http://wsl.localhost:7860   # works from WSL (WSLg Chrome)
# Windows Chrome: http://wsl.localhost:7860    # also works, no netsh needed
```

Use `wsl.localhost` over raw IPs wherever possible — IPs can change on WSL
restart; `wsl.localhost` does not.

### Why Windows Defender Firewall blocks CDP WebSocket **[+]**

All three Firewall profiles are enabled (Domain, Private, Public). The
specific failure mode when connecting to Windows Chrome CDP from WSL:
- `GET /json/version` (HTTP) → **succeeds** — TCP proxy forwards it fine
- WebSocket upgrade (`Connection: Upgrade`) → **Windows Defender resets**
  the connection at the application layer, non-deterministically

A `netsh portproxy` rule at the TCP level is not sufficient — it forwards
the initial HTTP but Defender still intercepts the WS upgrade.

This is exactly why the 5-retry pattern in old scripts "works sometimes" —
the block is probabilistic. The fix is to avoid the cross-boundary WebSocket
entirely using the WSLg path.

### The three paths — a companion project knew two, we have a third **[+]**

| Path | How | Runs where | CDP boundary | Cap target |
|---|---|---|---|---|
| **CDP from WSL** (fragile) | `connectOverCDP` → Windows Chrome | WSL | ✗ WS crosses boundary → Firewall resets | `--screen` |
| **Windows-native** (a companion project solution) | Copy project to `C:\`, Node on Windows | Windows | ✓ none | `--screen` or `--window` |
| **WSLg** ← recommended | `agent-browser --headed` Linux Chrome via WSLg | WSL | ✓ none | `--window` (specific window) |

WSLg is the cleanest: everything runs from WSL, nothing needs copying to
Windows, Cap captures just the Chrome window.

### WSLg requirements

WSLg ships with WSL 2 on Windows 11 and recent Windows 10 builds.
Verify it's running:
```bash
wsl.exe --version   # should show WSLg version line
echo $DISPLAY       # should be :0 or similar
xdpyinfo 2>&1 | head -1  # should show X.Org or Xwayland
```

If `DISPLAY` is unset, WSLg is not running. Fallback: use the Windows-native
path (run Node/agent-browser on Windows) or set up VcXsrv/Xming manually.

### `netsh portproxy` — when you actually need it

Required when a **Windows-side browser** needs to reach a **WSL-hosted
service** and `wsl.localhost` doesn't work (some corporate DNS setups block
it):

```powershell
# Windows admin PowerShell — one-time per port:
netsh interface portproxy add v4tov4 `
  listenport=<port> listenaddress=0.0.0.0 `
  connectport=<port> connectaddress=<wsl-ip>
# Windows Chrome then visits http://localhost:<port>
```

Not needed for the WSLg path — `agent-browser --headed` uses WSL's own
`localhost` and `wsl.localhost` directly.

### Tailscale — when HTTPS is actually required

`tailscale serve` was necessary in the a companion project project specifically
because WordPress generates absolute HTTPS URLs when configured with an
HTTPS site URL — plain `http://localhost` breaks script/asset loading.
Same applies to any app that:
- Sets `WP_HOME` / `WP_SITEURL` as HTTPS constants
- Uses `Secure` cookies that only transmit over HTTPS
- Enforces HSTS or mixed-content policies

```bash
# Windows PowerShell (admin):
tailscale serve --bg http://localhost:<port>
# Gives you: https://<hostname>.<tailnet>.ts.net
# That hostname also resolves from inside WSL (Tailscale DNS)
```

For recording purposes Tailscale is only needed when the target app itself
requires HTTPS. A plain Gradio app, Next.js dev server, or static site works
fine over HTTP with `wsl.localhost`.
