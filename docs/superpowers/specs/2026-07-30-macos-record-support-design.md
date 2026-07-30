# Design — macOS support for `capt record` (parity with Windows, then beyond)

Status: approved design, not yet implemented. Feeds into an implementation plan
via the `writing-plans` skill.

## Motivation

`capt`'s Record half only runs today via a WSL → Windows split: WSL orchestrates,
`win/beat_runner.py` runs as its own Python process on the Windows machine
(copied there by `win/install.ps1`), launching Chrome and Cap natively because
Windows Defender resets WebSocket connections that cross the WSL→Windows
boundary (see `docs/ARCHITECTURE.md`). That split — PowerShell hop, shared-file
handoff, `/mnt/c/...` path translation — exists *only* because of the WSL/Windows
boundary.

On macOS there is no such boundary: the agent, the browser (Playwright), and Cap
Desktop all run in one process on one machine. Cap ships a native macOS CLI
(`curl -fsSL https://cap.so/install-cli.sh | sh`) and Cap Desktop already stores
recordings under `~/Library/Application Support/so.cap.desktop.dev/recordings`
on macOS (confirmed in Cap's own `CONTRIBUTING.md`). The goal is not just parity
but to use that architectural simplicity to make the macOS path simpler and more
capable than the Windows one, and to fold in macOS-specific automation
capabilities (Accessibility API, global event capture) that have no Windows
equivalent in this codebase today.

This also doubles as the real test bed for the upstream `cap doc`/"Agent
Workflows" PR work prepared earlier in this project (`upstream/`,
`docs/upstream-proposal.md`) — the "record a multi-step walkthrough with
automatic zoom" workflow proposed there gets its first real end-to-end run on
this Mac, using this implementation.

## Reconciling "unify" vs. "build a separate macOS path"

The core beat-cycle logic — launch a browser, start `cap record --detach`,
drive steps, track markers, stop, build zoom segments, merge config, export —
is plain, OS-agnostic Python. `capt/zoom.py`, `capt/config.py`, and
`capt/export.py` already prove this: no OS branching in any of them. The only
genuinely OS-specific things are (a) how the beat-driving code gets invoked
(in-process on macOS/Linux vs. across the WSL→PowerShell→Windows boundary) and
(b) preflight checks. So the design unifies the core logic into one shared,
tested module and keeps only the invocation hop and preflight gates separate
per platform — see Phase 1 below.

## Phase 1 — shared beat core + macOS native path + auto-capture marking

This phase is fully specified and is what gets built first.

### Module layout

```
capt/record/
├── __init__.py
├── beat.py             # NEW — run_beat(): the shared, OS-agnostic beat cycle
├── steps.py             # NEW — scripted step schema (goto/click/wait/mark) + Playwright driver
└── macos_capture.py     # NEW — CGEventTap global click/key listener + hotkey-triggered labeled marks (macOS only)

capt/preflight.py         # becomes a dispatcher: common gates + OS-specific gates
capt/preflight_macos.py    # NEW
capt/preflight_windows.py  # NEW (extracted from today's capt/preflight.py)

win/beat_runner_entry.py   # NEW — thin shim: parse argv → call capt.record.beat.run_beat()
win/install.ps1            # extended: Copy-Item -Recurse the capt/ package tree to C:\cap-tools\capt\
                            # (same copy mechanism it already uses for win/*; no packaging/publishing needed)
win/beat_runner.py          # → moved to win/_archive/ (superseded; matches this repo's existing _archive convention)
```

`capt/zoom.py`, `capt/config.py`, `capt/export.py` are unchanged — `run_beat()`
calls them as-is.

### Data flow — one beat, either platform

`run_beat(url, steps, out_dir, screen_id, marker_source="steps", export_to=None)`:

1. Resolve the `cap` binary (existing `cap_bin()` in `capt/export.py`).
2. Launch Playwright Chromium, navigate to `url` (skipped entirely if
   `marker_source == "global-capture"` and no `url`/`steps` given — see below).
3. `cap record start --detach --json` — a single synchronous call, clean JSON
   parse. (This also replaces the stale Popen+sleep+scrape workaround identified
   in `win/beat_runner.py::_cap_start()` earlier this session — Cap's own CLI
   now blocks internally via a session-readiness poll and returns one clean
   JSON line, confirmed by reading `apps/cli/src/record.rs` in the upstream
   research. The shared `run_beat()` is written using the simple synchronous
   form; the old workaround is not carried forward.)
4. Create a marker tracker (`capt.zoom.create_tracker()`). Depending on
   `marker_source`:
   - `"steps"` — drive each step via Playwright, calling `tracker.mark(label)`
     on explicit `mark` steps and automatically on `click`/`fill` actions.
   - `"global-capture"` (macOS only) — `capt/record/macos_capture.py` installs a
     `CGEventTap` listening for real clicks/keystrokes system-wide and calls
     `tracker.mark()` for each one; a configurable hotkey (e.g. Cmd+Shift+M)
     calls `tracker.mark(label)` with a typed label instead of an auto label,
     without needing to alt-tab to a terminal. No `steps.json` is required —
     this is what enables a genuinely *manual* walkthrough (a human or an agent
     just does the thing) to still get automatic zoom.
   - Both sources can run together (scripted steps plus manual clicks on top).
5. `cap record stop --id <recordingId> --json`; require `recordingMetaExists`.
6. `cap project validate <path> --json`.
7. `build_zoom_segments(tracker.events())` → `read_config(path)` →
   `merge_zoom_segments` → `write_config(path, merged)`.
8. Optional `export()` if `export_to` is set.
9. Return `{recordingId, path, events, zoomSegments, exportPath?}`.

### Where it forks by platform

- **macOS/Linux:** `capt record` calls `run_beat()` directly, in-process. No
  file handoff, no serialization round trip — the concrete "simpler and more
  reliable than Windows" result of there being no process/OS boundary to cross.
- **Windows/WSL:** unchanged in spirit — WSL still preflights, then invokes
  `powershell.exe -Command "cd C:\cap-tools; python beat_runner_entry.py ..."`.
  `beat_runner_entry.py` is now a thin shim that imports the *same* `run_beat()`
  (vendored onto the Windows box by an extended `win/install.ps1`) instead of
  reimplementing the beat cycle. It writes the `BeatResult` to a shared file
  under `C:\recordings\...` for WSL to read back, same pattern as today.

### Preflight / error handling

- Common gates (all platforms): `cap doctor --json` → `captureReady`;
  `cap targets --json` → at least one screen; output directory writable.
- `preflight_macos.py`: Playwright/Chromium installed; if `marker_source`
  includes `"global-capture"`, also check the Accessibility permission
  (separate from Screen Recording — its own System Settings toggle). I'm not
  building a separate Screen Recording permission check — `cap doctor`'s
  `captureReady` should already reflect that, since Cap itself needs the
  permission to report ready. This assumption gets confirmed during the real
  test run in Phase 1's testing plan, not assumed silently.
- `preflight_windows.py`: unchanged — PowerShell reachable, Windows
  beat-runner ready (extracted verbatim from today's `capt/preflight.py`).
- `run_beat()` wraps the record/drive/stop sequence in try/finally so a
  mid-beat crash (browser crash, driver exception) still stops the Cap session
  instead of leaving it orphaned. A failed zoom-build or config-write logs a
  warning and still exports with whatever config exists — the deterministic
  recording should not be blocked by the polish step failing, mirroring the
  existing "AI is optional, core is deterministic" philosophy from the `guide`
  half of this project.

### Testing plan

- Unit tests (run now, no Cap/Playwright/macOS permissions needed): step-schema
  validation; `run_beat()`'s control flow with `subprocess.run` and Playwright
  mocked out, covering the start→drive→stop→zoom→export ordering and the
  stop-on-error path. Same style as the existing `tests/test_zoom.py` (10
  passing tests already cover `build_zoom_segments`/`merge_zoom_segments`).
- Real integration test on this Mac, once Screen Recording (and, for
  `global-capture`, Accessibility) permissions are granted: an actual
  `capt record` run producing a real `.cap` and exported `.mp4`. This is also
  the first real run of the upstream "record a multi-step walkthrough with
  automatic zoom" workflow end to end (see
  `docs/playbook-auto-zoom-recording.md`).
- Windows regression: cannot be tested from this machine. Flagged explicitly —
  `beat_runner_entry.py` plus the vendored `capt` package need to be verified on
  an actual WSL/Windows setup before that side is considered migrated; this
  spec does not claim it works until that's confirmed by the user.

## Phase 2 — live Accessibility-based window/tab logging (sequenced after Phase 1, `guide`-side)

Not a replacement for `guide/spike/detect_tabs.py` — a complementary source.
`detect_tabs.py` analyzes an *already-recorded* video after the fact, so it
works on any `.cap` regardless of platform or when it was recorded. Accessibility
APIs (`AXUIElementCopyAttributeValue`, `NSWorkspace` notifications) can only
observe *live*, during a recording happening on this Mac right now — a
fundamentally different data-capture point, not a drop-in swap.

Shape: `run_beat()` optionally logs `{elapsed_s, frontmost_app, window_title}`
samples via the Accessibility API alongside the click/key tracker (new module,
e.g. `capt/record/macos_window_log.py`). `capt/guide/structure.py` prefers this
live log when present (deterministic, free, no LLM) and falls back to
`detect_tabs.py`'s vision-based analysis otherwise (older recordings,
Windows-recorded ones, anything without the log).

Deliberately not detailed further here — this depends on the Accessibility
integration built in Phase 1 (`macos_capture.py`) actually working in practice.

## Phase 3 — native app automation (sequenced last, most exploratory)

Extends the step schema in `capt/record/steps.py` beyond Playwright/browser
actions to Accessibility-driven native-app actions, e.g.
`{"action": "ax-click", "app": "Notes", "role": "AXButton", "title": "New Note"}`.

This is the least proven of the four capabilities folded into this design:
matching UI elements in arbitrary native apps is heuristic (role/title-based),
not clean DOM selectors, and behavior varies a lot by app. Rather than design a
general schema blind, Phase 3 should start as *direction + one concrete
prototype app*, refined into its own design pass once there's a real
Accessibility integration (from Phase 1/2) to build on.

## Explicitly out of scope for now

- Fully unifying the Windows *invocation* (only the core logic is unified;
  the WSL→PowerShell→Windows hop stays, because the OS boundary is real).
- The "chain record → zoom → export → guide into one command" idea raised
  earlier in this project — a plausible future stretch goal, not part of this
  design.
- A general native-app step schema (that's Phase 3, sketched only).
