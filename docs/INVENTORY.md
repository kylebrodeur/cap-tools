# Inventory — Unique Items Across Projects

Every distinct technique, pattern, or finding gathered from cross-project
research. Each item is sourced and tagged for its role in the build.

**Tag legend:**
- `[CORE]` — foundational, used in every recording workflow
- `[BRIDGE]` — enables the WSL→Windows recording bridge
- `[POLISH]` — post-record quality improvements
- `[ASSEMBLE]` — video assembly pipeline
- `[PREFLIGHT]` — readiness checks
- `[PATTERN]` — design pattern / architectural choice

---

## 1. Cap CLI & Project Schema

**Source:** direct CLI introspection + real `.cap` files on disk

| # | Item | Tag |
|---|---|---|
| 1 | `cap record start --path beats/<name>.cap --detach --json` → saves `.cap` to explicit path | `[CORE]` |
| 2 | `--detach` returns `{recordingId, pid}` immediately; process is backgrounded — never use `execSync` | `[CORE]` |
| 3 | `cap record stop --id <recordingId> --json` stops the specific recording | `[CORE]` |
| 4 | `cap record status --json` → check for active sessions before starting | `[CORE]` |
| 5 | `cap record --window <id>` → record a specific OS window, not the full screen | `[BRIDGE]` |
| 6 | `cap record --screen <id>` → full screen fallback | `[CORE]` |
| 7 | `cap targets --json` → discover screens, windows, cameras, mics | `[CORE]` |
| 8 | `cap targets windows` returns `[]` when no windows are open; appears when window opens | `[BRIDGE]` |
| 9 | `cap project config get <proj.cap> --json` → read current `project-config.json` | `[POLISH]` |
| 10 | `cap project config set <proj.cap> --settings-json '...'` → write full config (omitted fields reset to defaults) | `[POLISH]` |
| 11 | `cap export <proj.cap> <out.mp4> --fps 60 --quality maximum --json` | `[CORE]` |
| 12 | `cap export --settings-json '{"format":"Mp4","fps":60,...}'` alternative to flags | `[CORE]` |
| 13 | Export streams NDJSON progress: `{"type":"Progress","rendered_count":N,"total_frames":N}` | `[CORE]` |
| 14 | `cap upload <file> --json` → shareable cap.so link | `[CORE]` |
| 15 | `cap screenshot --screen <id> --json` → quick still (pre/post verification) | `[PREFLIGHT]` |
| 16 | `cap doctor --json` → `{ok, captureReady}` → preflight gate | `[PREFLIGHT]` |
| 17 | `cap guide --json` → machine-readable capability manifest (schema source of truth) | `[CORE]` |

### `project-config.json` schema items

| # | Item | Tag |
|---|---|---|
| 18 | `timeline.zoomSegments[]` → auto-zoom without Studio. Fields: `{start, end, amount, mode:"auto", glideDirection, glideSpeed, instantAnimation, edgeSnapRatio}` | `[POLISH]` |
| 19 | `amount: 2.0` = strong demo zoom; `amount: 1.5` = subtle | `[POLISH]` |
| 20 | `mode: "auto"` → Cap tracks cursor in zoomed window automatically | `[POLISH]` |
| 21 | `background.source` types: `"wallpaper"` (path) / `"color"` (RGBA) | `[POLISH]` |
| 22 | Framed look: `padding: 10.0, rounding: 7.5, shadow: 73.6` | `[POLISH]` |
| 23 | Bundled wallpapers at `AppData\Local\Cap\assets\backgrounds\` | `[POLISH]` |
| 24 | `cursor.animationStyle: "mellow"` + `motionBlur: 0.5` = animated spring cursor | `[POLISH]` |
| 25 | `cursor.size: 100` (standard) / `200` (prominent) | `[POLISH]` |
| 26 | `screenMotionBlur` (0–1) + `screenMovementSpring {stiffness, damping, mass}` = zoom animation physics | `[POLISH]` |
| 27 | Snappy spring: `{200, 40, 2.25}` — Smooth/elastic: `{120, 14, 1.0}` | `[POLISH]` |
| 28 | `captions: null` / `keyboard: null` = disable overlays entirely | `[POLISH]` |
| 29 | `timeline.segments[].timescale` → speed ramp (1.0 = normal) | `[POLISH]` |
| 30 | `camera.hide: true` → suppress PiP overlay for screen-only recordings | `[POLISH]` |

---

## 2. The Bridge — WSLg + agent-browser + Cap Window Capture

**Source:** `claude-knowledge-explorer/.agents/skills/agent-browser/` + live WSL env discovery

This is the core architectural finding. All items here work together.

| # | Item | Tag |
|---|---|---|
| 31 | WSL has X11 display (`DISPLAY=:0`, X.Org running via WSLg) — Linux GUI apps render as Windows windows | `[BRIDGE]` |
| 32 | `agent-browser` installs its own Linux Chrome (`~/.agent-browser/browsers/chrome-*/chrome`, ELF 64-bit) | `[BRIDGE]` |
| 33 | `agent-browser --headed open <url>` → Chrome window rendered via WSLg, visible on Windows desktop | `[BRIDGE]` |
| 34 | `AGENT_BROWSER_HEADED=1` env var enables headed mode globally | `[BRIDGE]` |
| 35 | WSLg Chrome window appears in `cap targets windows` → can be window-captured by Cap | `[BRIDGE]` |
| 36 | `cap record --window <id>` captures the WSLg Chrome window with no desktop noise | `[BRIDGE]` |
| 37 | `agent-browser get cdp-url` → exposes the live CDP WebSocket URL of the running session | `[BRIDGE]` |
| 38 | The CDP URL from item 37 is available for additional tooling (zoom timestamp injection, Playwright fallback) but is NOT needed for Cap's recording path | `[BRIDGE]` |
| 39 | **No cross-boundary WebSocket needed** — agent-browser in WSL drives WSLg Chrome; Cap records the Windows window; they're fully independent | `[BRIDGE]` |
| 40 | `agent-browser record start ./debug.webm` → simultaneous in-browser WebM debug take while Cap records polished `.cap` | `[BRIDGE]` |
| 41 | `agent-browser record stop` → finalize debug WebM | `[BRIDGE]` |
| 42 | **Two-take pattern**: `agent-browser record` = quick debug artifact; `cap record` = polished publishable artifact | `[PATTERN]` |

---

## 3. agent-browser Automation Patterns

**Source:** `claude-knowledge-explorer/.agents/skills/agent-browser/`

| # | Item | Tag |
|---|---|---|
| 43 | `agent-browser open <url>` → navigate (auto-adds https://) | `[CORE]` |
| 44 | `agent-browser snapshot -i` → accessibility tree refs (`@e1`, `@e2`...) | `[CORE]` |
| 45 | `agent-browser click @e1` / `fill @e2 "text"` / `select` / `check` | `[CORE]` |
| 46 | `agent-browser wait --load networkidle` → wait for page to settle | `[CORE]` |
| 47 | `agent-browser wait --text "Ready"` / `wait @e1` / `wait 2000` | `[CORE]` |
| 48 | `agent-browser connect <ws-url>` → connect to external Chrome via CDP URL | `[BRIDGE]` |
| 49 | `agent-browser --auto-connect` → auto-discovers running Chrome via DevToolsActivePort | `[BRIDGE]` |
| 50 | `agent-browser --cdp <port>` → connect via CDP port (WSL → Windows Chrome fallback) | `[BRIDGE]` |
| 51 | Refs (`@e1`) are invalidated on navigation — always re-snapshot after page changes | `[PATTERN]` |
| 52 | `agent-browser set viewport 1920 1080` → set recording resolution | `[CORE]` |
| 53 | `agent-browser --color-scheme dark` → consistent dark mode for recording | `[CORE]` |
| 54 | `agent-browser eval --stdin <<'EOF' ... EOF` → inject JS for overlay dismissal, state reset | `[CORE]` |
| 55 | `agent-browser stream enable` → live WebSocket pixel stream (monitoring, not recording artifact) | `[BRIDGE]` |
| 56 | `agent-browser close` → shut down browser; always cleanup in trap/finally | `[CORE]` |
| 57 | `agent-browser diff screenshot --baseline before.png` → visual regression after a beat | `[PREFLIGHT]` |
| 58 | `agent-browser screenshot --annotate` → SoM screenshot with numbered element overlays (for model perception) | `[PATTERN]` |

---

## 4. CDP / Browser Patterns

**Source:** `an internal reference project` scripts + `a companion project` SESSION-LEARNINGS

| # | Item | Tag |
|---|---|---|
| 59 | CDP from WSL is unreliable — Windows Defender Firewall resets WebSocket connections unpredictably | `[PATTERN]` |
| 60 | `agent-browser --headed` (WSLg path) eliminates the WSL→Windows CDP problem entirely | `[BRIDGE]` |
| 61 | If connecting to Windows Chrome: must fetch `/json/version`, extract GUID from `webSocketDebuggerUrl`, rewrite `127.0.0.1` to `<gateway-ip>` | `[PATTERN]` |
| 62 | Gateway IP from WSL: `ip route show \| grep default \| awk '{print $3}'` | `[PATTERN]` |
| 63 | 5-retry pattern (HTTP fetch + WebSocket connect) for CDP-from-WSL path | `[PATTERN]` |
| 64 | `CDP Browser.getWindowForTarget` + `Browser.setWindowBounds {windowState: "maximized"}` → maximize via CDP without PowerShell | `[BRIDGE]` |
| 65 | Chrome `--app=<url>` mode → chromeless PWA window (alternative to WSLg; for Windows-native Chrome) | `[PATTERN]` |
| 66 | Chrome `--user-data-dir=/tmp/fresh-profile-$(date +%s)` → fresh session per recording take | `[CORE]` |

---

## 5. Beat Recording Patterns

**Source:** `an internal reference project/scripts/`

| # | Item | Tag |
|---|---|---|
| 67 | Beat = named logical segment, one `.cap` project per beat, clean in/out points | `[PATTERN]` |
| 68 | Beat loop: `cap record start` → drive beat → `cap record stop` → `cap project config set` → `cap export` | `[CORE]` |
| 69 | `capStartDetached`: spawn Cap to temp file, `sleep 2.5s`, parse file for `{recordingId}` | `[CORE]` |
| 70 | Cap JSON output may be multi-line or log-prefixed; parse with depth-tracking fallback | `[CORE]` |
| 71 | `isRecording()` guard: check `cap record status` before starting to avoid duplicate sessions | `[CORE]` |
| 72 | Beat registry: `{name: [stepFn, stepFn, ...]}` — compose beats from reusable step functions | `[PATTERN]` |
| 73 | Step functions: `beatLoad`, `beatSlice`, `beatPrint` etc — each drives one UI interaction phase | `[PATTERN]` |
| 74 | `--skip-cap` flag for driving UI without recording (dry run / rehearsal) | `[PATTERN]` |
| 75 | `--pause=N` between beats (seconds) for visual breathing room in recording | `[PATTERN]` |
| 76 | Hold 4s after last beat for closing shot before stopping recording | `[PATTERN]` |
| 77 | Re-record single beat without redoing entire take — independence is the key value | `[PATTERN]` |

---

## 6. Overlay Dismissal & State Reset

**Source:** `an internal reference project` scripts

| # | Item | Tag |
|---|---|---|
| 78 | HF Space header removal via `document.getElementById('huggingface-space-header')?.remove()` | `[CORE]` |
| 79 | Cookie/consent banner heuristic: match innerText `/(cookie\|accept\|privacy)/i`, remove if `text.length < 400` | `[CORE]` |
| 80 | Auto-click dismiss buttons matching `/(accept\|allow all\|got it\|agree\|ok\|dismiss\|close)/i` | `[CORE]` |
| 81 | Run dismissal in a polling loop for 6-8s after page load (banners appear async) | `[PATTERN]` |
| 82 | Run dismissal again once before each beat starts (post-navigation banners) | `[PATTERN]` |
| 83 | With agent-browser: `agent-browser eval --stdin` for JS injection (avoids shell quoting issues) | `[CORE]` |
| 84 | Demo state reset command pattern: `git checkout -- data/file.jsonl && rm -f data/cache.json` | `[PATTERN]` |

---

## 7. Preflight Gates

**Source:** `an internal reference project/scripts/record_preflight.py`

| # | Item | Tag |
|---|---|---|
| 85 | G1: `cap doctor --json` → `captureReady: true` | `[PREFLIGHT]` |
| 86 | G2: `cap targets --json` → at least one screen target | `[PREFLIGHT]` |
| 87 | G3: `agent-browser --version` → installed and runnable | `[PREFLIGHT]` |
| 88 | G4: URL HTTP check → 200/301/302 OK; 401/403 = reachable (HF block, not failure) | `[PREFLIGHT]` |
| 89 | G5: output directory exists and is writable | `[PREFLIGHT]` |
| 90 | G6 (optional): `agent-browser get url` after opening target — page loaded OK | `[PREFLIGHT]` |
| 91 | Pre-recording checklist (from pi-tools): clean state, font legibility test-record, script what you'll type | `[PREFLIGHT]` |

---

## 8. Zoom Segment Generation from Event Timestamps

**Source:** synthesis (an internal reference project's zoom segments + agent-browser event tracking)

| # | Item | Tag |
|---|---|---|
| 92 | Collect event timestamps during automation: `{type, elapsed_seconds}` per click/nav/action | `[POLISH]` |
| 93 | Wrap agent-browser commands in a timing tracker: record elapsed since `cap record start` | `[POLISH]` |
| 94 | Build zoom segments: `{start: t-0.5, end: t+2.5, amount: 2.0, mode: "auto", ...}` per significant event | `[POLISH]` |
| 95 | Merge overlapping segments: if gap between events < 1.0s, merge into one longer zoom | `[POLISH]` |
| 96 | Apply segments after recording: `cap project config set` with built config | `[POLISH]` |
| 97 | `mode: "auto"` = Cap follows cursor during zoom; no need to specify coordinates | `[POLISH]` |

---

## 9. Video Assembly Pipeline

**Source:** `an internal reference project/scripts/assemble-video.py`

| # | Item | Tag |
|---|---|---|
| 98 | Manifest JSON: `{output_resolution, output_fps, output, segments[]}` | `[ASSEMBLE]` |
| 99 | Segment types: `camera` (no caption) / `screen` (video + optional VO audio + optional caption) | `[ASSEMBLE]` |
| 100 | Per-segment ffmpeg: scale/pad to output resolution, `tpad=stop_mode=clone` to match VO duration | `[ASSEMBLE]` |
| 101 | Caption: `drawtext=fontfile=...:textfile=...:...` burned at `y=h-text_h-40` (bottom safe zone) | `[ASSEMBLE]` |
| 102 | `ffprobe` for duration and audio stream detection | `[ASSEMBLE]` |
| 103 | Two-pass assembly: render segments to temp dir → `ffmpeg -f concat` | `[ASSEMBLE]` |
| 104 | Output dimensions must be even (H.264 requirement) — round up if odd | `[ASSEMBLE]` |
| 105 | `libx264 -preset fast -crf 18` for quality/speed balance | `[ASSEMBLE]` |
| 106 | VO audio can be shorter or longer than video — pad/trim to match | `[ASSEMBLE]` |

---

## 10. Recurring Demo Structure (5+ Projects)

**Sources:** an internal reference project, spanish-tutor, audio-transcription, brain-tree-os, mcp-network-analyzer

| # | Item | Tag |
|---|---|---|
| 107 | Universal structure: open (camera, ~20s) → beats (screen, 1-3 per feature) → close (camera, ~15s) | `[PATTERN]` |
| 108 | VO file per beat (WAV) — one spoken sentence per screen section | `[PATTERN]` |
| 109 | "Climbing job" / compelling demo state: reset to baseline before take so the interesting thing actually happens | `[PATTERN]` |
| 110 | Beat-level granularity: polish only the 2-3 beats that carry the story; rest are raw exports | `[PATTERN]` |
| 111 | Camera footage: open and close are independent, can be re-recorded without redoing screen beats | `[PATTERN]` |

---

## 11. Terminal Recording (Pi/TUI Demos)

**Source:** `pi-tools/docs/demo-architecture-patterns.md`

| # | Item | Tag |
|---|---|---|
| 112 | Terminal A (control/Pi session) = primary Cap recording target | `[PATTERN]` |
| 113 | Terminal B (live dashboard) = ambient cutaway — use as separate beat or PiP | `[PATTERN]` |
| 114 | State bridge: write `state.json` every tick; Terminal B polls it at 200ms | `[PATTERN]` |
| 115 | ANSI in-place redraws (`\x1b[2J\x1b[H`) for live dashboard feel | `[PATTERN]` |
| 116 | Font legibility test: record a 30s test clip before the real take | `[PREFLIGHT]` |
| 117 | Script all typed commands — no freestyle CLI on camera | `[PREFLIGHT]` |
| 118 | Offline resilience beat: disconnect network, submit job, show fallback model runs | `[PATTERN]` |
