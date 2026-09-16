# Runbook — ReelBinder interface demo re-take on the Windows machine

Context: the first take was recorded in main Chrome instead of the installed
Google PWA app shell and was rejected. This runbook records the real app
shell, natively on Windows. Steps source (already capt-verified, 56/56
beats): `slate/scripts/demo-interface.steps.json` in the slate repo.

## Why native Windows, not WSL

Prior testing (docs/FINDINGS.md §7–8) showed CDP from WSL to Windows Chrome
fails unpredictably at the WebSocket layer (Defender resets, non-deterministic),
and the CDP WebSocket URL needs a dynamic GUID rewrite to even attempt it.
**Run capt natively on Windows** — Python on Windows, Chrome on Windows, no
cross-boundary anything. The WSL bridge (`win/`) is only for `capt record`'s
PowerShell hop, not for this flow.

## One-time setup on the Windows machine

```powershell
# 1. Cap Desktop 0.6+ installed, its cap CLI on PATH (check: cap --version)
# 2. cap-tools + deps, native Windows Python:
cd C:\path\to\cap-tools
pip install -e .
python -m playwright install chromium
# 3. ffmpeg on PATH (needed for section cuts later):
winget install Gyan.FFmpeg
```

## Capture run — the installed PWA app shell

```powershell
# 1. Quit ALL Chrome instances first (profile lock + window enumeration
#    misbehave with two running).
# 2. Launch the PWA in app-mode with a debugging port:
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --app="http://localhost:8080" `
  --remote-debugging-port=9222 `
  --user-data-dir="C:\temp\pwa-profile" `
  --window-size=1707,1067 --window-position=0,0 `
  --no-first-run --no-default-browser-check
#    (localhost:8080 = slate dev server via `npm run dev` in slate/; use
#     --app=https://studio.reelbinder.app/ for the hosted build instead)

# 3. Fresh window ID every launch — NEVER cache it across takes:
cap record windows --json
#    → the window named after the app ("ReelBinder")

# 4. Record that window while capt drives the SAME instance over CDP:
uv run capt record --window <fresh-id> `
  --steps <path-to>\slate\scripts\demo-interface.steps.json `
  --cdp http://127.0.0.1:9222 `
  --out <artifacts-dir> --beat reelbinder-interface
#    ~6.5 min; ends cleanly on its own. Same-instance CDP is native-to-
#    native on Windows (127.0.0.1), so the WSL WebSocket flake does not apply.

# 5. Verify completeness BEFORE anything else:
python -c "import json; b=json.load(open('<artifacts-dir>/reelbinder-interface.beats.json')); print('complete:', b['complete']); [print(' FAIL', x['label'], x['error']) for x in b['beats'] if not x['ok']]"
```

The take is **raw only** at this point — Kyle reviews the raw pass before
any styling.

## Styling (only after Kyle approves the raw take)

```powershell
# 3D scene + zoom onto the full take:
uv run capt scene apply <artifacts-dir>\reelbinder-interface.cap `
  <artifacts-dir>\reelbinder-interface.events.json --style reveal --yes
uv run capt zoom apply <artifacts-dir>\reelbinder-interface.cap `
  <artifacts-dir>\reelbinder-interface.events.json

# Export — FIRST export of a fresh .cap strips camera3dSegments (Cap's
# publish pass): warmup once, re-apply the scene, then export for real.
cap export <artifacts-dir>\reelbinder-interface.cap warmup.mp4 --json
uv run capt scene apply <artifacts-dir>\reelbinder-interface.cap `
  <artifacts-dir>\reelbinder-interface.events.json --style reveal --yes
cap export <artifacts-dir>\reelbinder-interface.cap reelbinder-interface-styled.mp4 --json

# Labeled sections for the demo timeline (18 beats → 18 MP4s):
uv run capt section list reelbinder-interface.beats.json --labeled-only
uv run capt section cut reelbinder-interface-styled.mp4 `
  reelbinder-interface.beats.json --labeled-only --out sections
```

## Troubleshooting

- `cap record windows` returns `[]` or misses the app window → stale
  ScreenCaptureKit/session state or the window is minimized; quit and
  relaunch Chrome in app mode, re-list immediately before recording.
- Window ID churns between listing and recording → take the ID in the same
  shell, immediately before `capt record`.
- Beats report says `complete: false` → the failing beat and its error are
  in the report; fix the selector/pacing in the steps file and re-run the
  whole take (takes are cheap; broken takes are not salvageable).