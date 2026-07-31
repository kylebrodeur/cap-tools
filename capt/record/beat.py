"""Shared, OS-agnostic beat cycle: record -> drive/capture -> stop -> zoom -> export.

Runs in-process on macOS/Linux (capt/cli.py calls run_beat() directly). On
Windows this same module is vendored onto the Windows machine (see
win/install.ps1) and invoked by win/beat_runner_entry.py via PowerShell from
WSL — see docs/superpowers/specs/2026-07-30-macos-record-support-design.md.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from capt.config import read_config, write_config
from capt.export import cap_bin, export as cap_export
from capt.zoom import build_zoom_segments, create_tracker, merge_zoom_segments


@dataclass
class BeatResult:
    recording_id: str
    cap_path: str
    events: list
    zoom_segments: list
    export_path: Optional[str] = None


def _run_cap_json(*args: str, timeout: int = 30) -> dict:
    """Run `cap <args> --json` and parse its JSON response — compact
    single-line (record start/stop) or pretty-printed multi-line
    (project validate) alike.

    Raises RuntimeError with the command's error output on failure, so a
    beat's failure reason is always visible, never swallowed.
    """
    proc = subprocess.run(
        [cap_bin(), *args, "--json"],
        capture_output=True, text=True, timeout=timeout,
    )
    out = proc.stdout.strip()
    if proc.returncode != 0:
        raise RuntimeError(f"cap {' '.join(args)} failed: {proc.stderr.strip() or out}")
    if not out:
        return {}
    # Whole output is a single JSON value — the common case, compact or
    # pretty-printed alike.
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        pass
    # Fallback: skip any non-JSON preamble, then track brace/bracket depth
    # to isolate the JSON payload from surrounding log noise.
    depth = 0
    buf = []
    started = False
    for line in out.splitlines():
        stripped = line.strip()
        if not started:
            if stripped.startswith("{") or stripped.startswith("["):
                started = True
        if started:
            buf.append(line)
            depth += stripped.count("{") + stripped.count("[") - stripped.count("}") - stripped.count("]")
            if depth == 0 and buf:
                try:
                    return json.loads("\n".join(buf))
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"cap {' '.join(args)} returned unparseable output: {out!r}") from e
    raise RuntimeError(f"cap {' '.join(args)} returned unparseable output: {out!r}")


def _start_recording(cap_path: str, screen_id: Optional[str], window_id: Optional[str] = None) -> dict:
    args = ["record", "start", "--detach", "--path", cap_path]
    if window_id:
        args += ["--window", window_id]
    elif screen_id:
        args += ["--screen", screen_id]
    event = _run_cap_json(*args)
    if "recordingId" not in event:
        raise RuntimeError(f"cap record start did not return a recordingId: {event}")
    return event


def _stop_recording(recording_id: str) -> dict:
    event = _run_cap_json("record", "stop", "--id", recording_id)
    if not event.get("recordingMetaExists"):
        raise RuntimeError(f"cap record stop did not confirm recordingMetaExists: {event}")
    return event


def _validate_project(cap_path: str) -> dict:
    return _run_cap_json("project", "validate", cap_path)


def run_beat(
    url: Optional[str],
    steps: list,
    out_dir: str,
    name: str = "full",
    screen_id: Optional[str] = None,
    window_id: Optional[str] = None,
    marker_source: str = "steps",
    zoom_amount: float = 2.0,
    export_to: Optional[str] = None,
) -> BeatResult:
    """Run one beat: record, drive/capture markers, stop, build+merge zoom,
    optionally export.

    marker_source: "steps" (drive `steps` via Playwright, marking on click/
    fill/goto/explicit-mark actions), "global-capture" (macOS-only — capture
    real clicks/keystrokes system-wide via capt.record.macos_capture, no
    steps.json required), or "steps+global-capture" for both at once.

    window_id, when given, captures that specific window instead of the
    whole screen (screen_id is ignored in that case) — narrower capture
    scope for a single browser window rather than the full display.
    """
    from capt.record.steps import drive_steps

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    cap_path = str(out_path / f"{name}.cap")

    sources = marker_source.split("+")

    started = _start_recording(cap_path, screen_id, window_id=window_id)
    recording_id = started["recordingId"]

    # The marker clock must be anchored to when the recording actually
    # started, not to whenever this function happened to be called —
    # _start_recording() blocks on Cap's session-readiness poll, which can
    # take real time. Creating the tracker (and starting global-capture)
    # only after the recording call returns keeps every elapsed_s offset
    # accurate relative to the recording's own timeline. All of this lives
    # inside the try/finally below so a failure anywhere in setup (e.g.
    # GlobalCapture.start() hitting a missing Input Monitoring permission)
    # still stops the already-running Cap session instead of orphaning it.
    capture = None
    try:
        tracker = create_tracker()

        if "global-capture" in sources:
            from capt.record.macos_capture import GlobalCapture
            capture = GlobalCapture(tracker)
            capture.start()

        if "steps" in sources and (url or steps):
            drive_steps(url, steps, tracker)
    finally:
        try:
            if capture is not None:
                capture.stop()
        finally:
            _stop_recording(recording_id)

    _validate_project(cap_path)

    events = tracker.events()
    zoom_segments = build_zoom_segments(events, amount=zoom_amount)
    try:
        current = read_config(cap_path)
        merged = merge_zoom_segments(current, zoom_segments)
        write_config(cap_path, merged)
    except (Exception, SystemExit) as e:
        print(f"⚠ zoom/config step failed, continuing without it: {e}")

    export_path = None
    if export_to:
        result = cap_export(cap_path, export_to)
        export_path = result.get("path", export_to)

    return BeatResult(
        recording_id=recording_id,
        cap_path=cap_path,
        events=events,
        zoom_segments=zoom_segments,
        export_path=export_path,
    )
