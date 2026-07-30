# macOS Record Support (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `capt record` a native, in-process macOS/Linux path (shared beat-cycle core, no PowerShell/WSL hop) with an auto-capture marker source, while leaving the existing Windows/WSL path working unchanged.

**Architecture:** Extract the OS-agnostic beat cycle (launch browser → `cap record start --detach` → drive/capture markers → stop → build+merge zoom → optional export) into `capt/record/beat.py::run_beat()`. `capt/cli.py`'s `record` command calls it directly on macOS/Linux; on WSL it still shells out via PowerShell, now to a thin `win/beat_runner_entry.py` shim that imports the same `run_beat()` (vendored onto Windows via `pip install -e`). Also extracts `capt/guide/pipeline.py::run_guide()` from `cli.py`'s `guide` command, and splits `capt/preflight.py`'s one Windows-specific gate out into `preflight_windows.py`, adding a macOS-only gate for the new capture permission.

**Tech Stack:** Python 3.11+, click, Playwright (sync API), pyobjc-framework-Quartz (macOS global event capture), pytest.

## Global Constraints

- Python 3.11+ (per `pyproject.toml`'s `requires-python`).
- No new runtime dependency without adding it to `pyproject.toml`'s `dependencies` (or the Windows-side `win/requirements.txt`, which Task 8 replaces with a `pip install -e` of the whole `capt` package instead).
- `capt/zoom.py`, `capt/config.py`, `capt/export.py` are not modified — `run_beat()` calls them as they exist today, verified in this session.
- The `cap` CLI's `--detach --json` returns one clean JSON line synchronously (confirmed by reading `record.rs` upstream) — no sleep/temp-file/scrape workaround anywhere in new code.
- `cap project config set` replaces the whole document — any config write goes through `read_config` → `merge_zoom_segments` → `write_config`, never a partial object (already established in `capt/zoom.py::merge_zoom_segments`).
- Windows behavior must not regress: `capt/cli.py`'s `record` command still does exactly what it does today when invoked from WSL. This plan cannot be verified against a real Windows box from this session — Task 8's final step says so explicitly and requires the user's own confirmation.
- Global capture (CGEventTap) needs the **Input Monitoring** permission (System Settings → Privacy & Security → Input Monitoring), not Accessibility — Accessibility is what Phase 2/3's AXUIElement-based work will need later. Keep this distinction correct in code comments and error messages; getting it wrong sends the user to the wrong settings pane.

---

### Task 1: `capt/record` package + step schema validation

**Files:**
- Create: `capt/record/__init__.py`
- Create: `capt/record/steps.py`
- Test: `tests/test_steps.py`

**Interfaces:**
- Produces: `VALID_ACTIONS: set[str]`, `validate_steps(steps: list[dict]) -> list[dict]` (raises `ValueError` on the first invalid step, otherwise returns `steps` unchanged).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_steps.py
import pytest

from capt.record.steps import validate_steps


def test_validate_steps_accepts_valid_goto():
    validate_steps([{"action": "goto", "url": "https://example.com"}])


def test_validate_steps_accepts_valid_click():
    validate_steps([{"action": "click", "selector": "#save"}])


def test_validate_steps_accepts_valid_fill():
    validate_steps([{"action": "fill", "selector": "#name", "text": "Kyle"}])


def test_validate_steps_accepts_valid_wait_variants():
    validate_steps([{"action": "wait", "selector": "#ready"}])
    validate_steps([{"action": "wait", "ms": 500}])
    validate_steps([{"action": "wait", "text": "Done"}])


def test_validate_steps_accepts_valid_mark():
    validate_steps([{"action": "mark", "label": "opened-settings"}])


def test_validate_steps_rejects_unknown_action():
    with pytest.raises(ValueError, match="unknown action"):
        validate_steps([{"action": "teleport"}])


def test_validate_steps_rejects_goto_without_url():
    with pytest.raises(ValueError, match="'goto' requires 'url'"):
        validate_steps([{"action": "goto"}])


def test_validate_steps_rejects_click_without_selector():
    with pytest.raises(ValueError, match="'click' requires 'selector'"):
        validate_steps([{"action": "click"}])


def test_validate_steps_rejects_fill_without_text():
    with pytest.raises(ValueError, match="'fill' requires"):
        validate_steps([{"action": "fill", "selector": "#x"}])


def test_validate_steps_rejects_wait_without_condition():
    with pytest.raises(ValueError, match="'wait' requires"):
        validate_steps([{"action": "wait"}])


def test_validate_steps_rejects_mark_without_label():
    with pytest.raises(ValueError, match="'mark' requires 'label'"):
        validate_steps([{"action": "mark"}])


def test_validate_steps_error_identifies_step_index():
    with pytest.raises(ValueError, match="step 1"):
        validate_steps([
            {"action": "goto", "url": "https://example.com"},
            {"action": "click"},
        ])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kylebrodeur/workspace/cap-tools && uv run pytest tests/test_steps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capt.record'`

- [ ] **Step 3: Create the package and implement `validate_steps`**

```python
# capt/record/__init__.py
```

(empty file — marks `capt/record` as a package)

```python
# capt/record/steps.py
"""Beat step schema (goto/click/fill/wait/mark) and the Playwright driver
that executes them against a live page, marking a shared event tracker as it
goes. See docs/superpowers/specs/2026-07-30-macos-record-support-design.md.
"""

VALID_ACTIONS = {"goto", "click", "fill", "wait", "mark"}


def validate_steps(steps: list) -> list:
    """Validate a list of step dicts, raising ValueError on the first problem.

    Schema:
        goto:  {"action": "goto", "url": str}
        click: {"action": "click", "selector": str}
        fill:  {"action": "fill", "selector": str, "text": str}
        wait:  {"action": "wait", "selector": str} |
               {"action": "wait", "ms": int} |
               {"action": "wait", "text": str}
        mark:  {"action": "mark", "label": str}
    """
    for i, step in enumerate(steps):
        action = step.get("action")
        if action not in VALID_ACTIONS:
            raise ValueError(
                f"step {i}: unknown action {action!r} "
                f"(expected one of {sorted(VALID_ACTIONS)})"
            )
        if action == "goto" and not step.get("url"):
            raise ValueError(f"step {i}: 'goto' requires 'url'")
        if action == "click" and not step.get("selector"):
            raise ValueError(f"step {i}: 'click' requires 'selector'")
        if action == "fill" and not (step.get("selector") and "text" in step):
            raise ValueError(f"step {i}: 'fill' requires 'selector' and 'text'")
        if action == "wait" and not any(k in step for k in ("selector", "ms", "text")):
            raise ValueError(f"step {i}: 'wait' requires one of 'selector', 'ms', 'text'")
        if action == "mark" and not step.get("label"):
            raise ValueError(f"step {i}: 'mark' requires 'label'")
    return steps
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_steps.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add capt/record/__init__.py capt/record/steps.py tests/test_steps.py
git commit -m "Add capt/record package with beat step schema validation"
```

---

### Task 2: Playwright step driver

**Files:**
- Modify: `capt/record/steps.py`
- Test: `tests/test_steps.py`

**Interfaces:**
- Consumes: `validate_steps` (Task 1).
- Produces: `_run_step(page, step: dict, tracker) -> None`, `drive_steps(url: str | None, steps: list[dict], tracker) -> None`. `tracker` is any object with `.mark(label: str) -> None` (matches `capt.zoom.create_tracker()`'s return value).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_steps.py
from unittest.mock import MagicMock, patch

from capt.record.steps import _run_step, drive_steps


def test_run_step_click_calls_page_and_marks_tracker():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "click", "selector": "#save"}, tracker)
    page.click.assert_called_once_with("#save")
    tracker.mark.assert_called_once_with("click:#save")


def test_run_step_fill_calls_page_and_marks_tracker():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "fill", "selector": "#name", "text": "Kyle"}, tracker)
    page.fill.assert_called_once_with("#name", "Kyle")
    tracker.mark.assert_called_once_with("fill:#name")


def test_run_step_goto_calls_page_and_marks_tracker():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "goto", "url": "https://example.com"}, tracker)
    page.goto.assert_called_once_with("https://example.com")
    tracker.mark.assert_called_once_with("goto")


def test_run_step_mark_uses_given_label_only():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "mark", "label": "opened-settings"}, tracker)
    tracker.mark.assert_called_once_with("opened-settings")
    page.click.assert_not_called()


def test_run_step_wait_ms_calls_wait_for_timeout():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "wait", "ms": 500}, tracker)
    page.wait_for_timeout.assert_called_once_with(500)
    tracker.mark.assert_not_called()


def test_run_step_wait_selector_calls_wait_for_selector():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "wait", "selector": "#ready"}, tracker)
    page.wait_for_selector.assert_called_once_with("#ready")


def test_run_step_wait_text_calls_wait_for_selector_with_text_prefix():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "wait", "text": "Done"}, tracker)
    page.wait_for_selector.assert_called_once_with("text=Done")


def test_drive_steps_launches_browser_navigates_and_closes():
    tracker = MagicMock()
    fake_page = MagicMock()
    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page
    fake_chromium = MagicMock()
    fake_chromium.launch.return_value = fake_browser
    fake_pw = MagicMock()
    fake_pw.chromium = fake_chromium
    fake_pw_cm = MagicMock()
    fake_pw_cm.__enter__.return_value = fake_pw
    fake_pw_cm.__exit__.return_value = False

    with patch("capt.record.steps.sync_playwright", return_value=fake_pw_cm):
        drive_steps("https://example.com", [{"action": "click", "selector": "#go"}], tracker)

    fake_page.goto.assert_called_once_with("https://example.com")
    fake_page.click.assert_called_once_with("#go")
    fake_browser.close.assert_called_once()


def test_drive_steps_closes_browser_even_if_a_step_raises():
    tracker = MagicMock()
    fake_page = MagicMock()
    fake_page.click.side_effect = RuntimeError("boom")
    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page
    fake_chromium = MagicMock()
    fake_chromium.launch.return_value = fake_browser
    fake_pw = MagicMock()
    fake_pw.chromium = fake_chromium
    fake_pw_cm = MagicMock()
    fake_pw_cm.__enter__.return_value = fake_pw
    fake_pw_cm.__exit__.return_value = False

    with patch("capt.record.steps.sync_playwright", return_value=fake_pw_cm):
        with pytest.raises(RuntimeError, match="boom"):
            drive_steps(None, [{"action": "click", "selector": "#go"}], tracker)

    fake_browser.close.assert_called_once()


def test_drive_steps_skips_navigation_when_no_url():
    tracker = MagicMock()
    fake_page = MagicMock()
    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page
    fake_chromium = MagicMock()
    fake_chromium.launch.return_value = fake_browser
    fake_pw = MagicMock()
    fake_pw.chromium = fake_chromium
    fake_pw_cm = MagicMock()
    fake_pw_cm.__enter__.return_value = fake_pw
    fake_pw_cm.__exit__.return_value = False

    with patch("capt.record.steps.sync_playwright", return_value=fake_pw_cm):
        drive_steps(None, [{"action": "mark", "label": "manual-step"}], tracker)

    fake_page.goto.assert_not_called()
    tracker.mark.assert_called_once_with("manual-step")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_steps.py -v`
Expected: FAIL — `ImportError: cannot import name '_run_step'`

- [ ] **Step 3: Implement the driver**

```python
# add to capt/record/steps.py, after VALID_ACTIONS/validate_steps
from playwright.sync_api import sync_playwright


def _run_step(page, step: dict, tracker) -> None:
    action = step["action"]
    if action == "goto":
        page.goto(step["url"])
        tracker.mark(step.get("label", "goto"))
    elif action == "click":
        page.click(step["selector"])
        tracker.mark(step.get("label", f"click:{step['selector']}"))
    elif action == "fill":
        page.fill(step["selector"], step["text"])
        tracker.mark(step.get("label", f"fill:{step['selector']}"))
    elif action == "wait":
        if "selector" in step:
            page.wait_for_selector(step["selector"])
        elif "text" in step:
            page.wait_for_selector(f"text={step['text']}")
        elif "ms" in step:
            page.wait_for_timeout(step["ms"])
    elif action == "mark":
        tracker.mark(step["label"])


def drive_steps(url, steps: list, tracker) -> None:
    """Launch Playwright Chromium, optionally navigate to url, then drive
    each step in order, marking `tracker` as described in `_run_step`.

    Always closes the browser, even if a step raises.
    """
    validate_steps(steps)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            page = browser.new_page()
            if url:
                page.goto(url)
                tracker.mark("page-load")
            for step in steps:
                _run_step(page, step, tracker)
        finally:
            browser.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_steps.py -v`
Expected: 21 passed

- [ ] **Step 5: Commit**

```bash
git add capt/record/steps.py tests/test_steps.py
git commit -m "Add Playwright step driver to capt/record/steps.py"
```

---

### Task 3: macOS global capture (CGEventTap + hotkey marking)

**Files:**
- Create: `capt/record/macos_capture.py`
- Modify: `pyproject.toml` (add `pyobjc-framework-Quartz` dependency, macOS-only)
- Test: `tests/test_macos_capture.py`

**Interfaces:**
- Produces: `is_hotkey_event(event_type: int, flags: int, keycode: int) -> bool`, `GlobalCapture(tracker, label_prefix: str = "click")` with `.start() -> None` (raises `PermissionError` if Input Monitoring isn't granted) and `.stop() -> None`.
- Consumes: `tracker.mark(label: str)` (matches `capt.zoom.create_tracker()`).

This task only runs its full test suite on macOS — guard accordingly.

- [ ] **Step 1: Add the platform-specific dependency**

Edit `pyproject.toml`'s `dependencies` list:

```toml
dependencies = [
    "click>=8.0",
    "playwright>=1.40",
    "pyobjc-framework-Quartz>=10.0; sys_platform == 'darwin'",
]
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_macos_capture.py
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only module")

from capt.record.macos_capture import GlobalCapture, is_hotkey_event, HOTKEY_FLAGS, HOTKEY_KEYCODE
import Quartz


def test_is_hotkey_event_matches_cmd_shift_m():
    assert is_hotkey_event(Quartz.kCGEventKeyDown, HOTKEY_FLAGS, HOTKEY_KEYCODE) is True


def test_is_hotkey_event_rejects_wrong_keycode():
    assert is_hotkey_event(Quartz.kCGEventKeyDown, HOTKEY_FLAGS, 99) is False


def test_is_hotkey_event_rejects_missing_modifier():
    assert is_hotkey_event(Quartz.kCGEventKeyDown, Quartz.kCGEventFlagMaskShift, HOTKEY_KEYCODE) is False


def test_is_hotkey_event_rejects_non_keydown_type():
    assert is_hotkey_event(Quartz.kCGEventKeyUp, HOTKEY_FLAGS, HOTKEY_KEYCODE) is False


def test_is_hotkey_event_ignores_extra_flags():
    # Caps lock or other incidental flags shouldn't break the match, as long
    # as Cmd+Shift are both present.
    extra = HOTKEY_FLAGS | Quartz.kCGEventFlagMaskAlphaShift
    assert is_hotkey_event(Quartz.kCGEventKeyDown, extra, HOTKEY_KEYCODE) is True


def test_global_capture_start_raises_permission_error_without_input_monitoring():
    # On a fresh checkout, this terminal/process has not been granted Input
    # Monitoring yet, so CGEventTapCreate returns None and start() must raise
    # a clear, actionable error rather than silently doing nothing.
    capture = GlobalCapture(tracker=None)
    with pytest.raises(PermissionError, match="Input Monitoring"):
        capture.start()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_macos_capture.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capt.record.macos_capture'`

- [ ] **Step 4: Implement the module**

```python
# capt/record/macos_capture.py
"""Global click/keystroke capture for macOS — an alternative marker source
to scripted Playwright steps, so a manual walkthrough (no steps.json) still
produces automatic zoom segments.

Requires the "Input Monitoring" permission (System Settings > Privacy &
Security > Input Monitoring) for whatever terminal/app this runs from. This
is a DIFFERENT permission from "Accessibility" — Accessibility is what
Phase 2/3's AXUIElement-based window inspection and native-app automation
will need later, not this module.
"""

import threading
from typing import Optional

import Quartz

HOTKEY_FLAGS = Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift
HOTKEY_KEYCODE = 46  # 'm' on a standard US keyboard layout


def is_hotkey_event(event_type: int, flags: int, keycode: int) -> bool:
    """Pure matcher: does this raw key-down event match the mark hotkey
    (Cmd+Shift+M)? Kept separate from the CGEventTap wiring so it's testable
    without a live tap or granted permission. Extra flags (e.g. Caps Lock)
    are tolerated as long as Cmd+Shift are both present.
    """
    return (
        event_type == Quartz.kCGEventKeyDown
        and (flags & HOTKEY_FLAGS) == HOTKEY_FLAGS
        and keycode == HOTKEY_KEYCODE
    )


class GlobalCapture:
    """Installs a CGEventTap for the lifetime of start()/stop(), marking
    `tracker` on every left/right mouse click and on the mark hotkey."""

    def __init__(self, tracker, label_prefix: str = "click"):
        self.tracker = tracker
        self.label_prefix = label_prefix
        self._tap = None
        self._run_loop = None
        self._run_loop_source = None
        self._thread: Optional[threading.Thread] = None

    def _callback(self, proxy, event_type, event, refcon):
        if event_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventRightMouseDown):
            self.tracker.mark(self.label_prefix)
        elif event_type == Quartz.kCGEventKeyDown:
            flags = Quartz.CGEventGetFlags(event)
            keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
            if is_hotkey_event(event_type, flags, keycode):
                self.tracker.mark("manual-mark")
        return event

    def start(self) -> None:
        mask = (
            Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown)
            | Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        )
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )
        if self._tap is None:
            raise PermissionError(
                "Could not create a global event tap — grant Input Monitoring "
                "to this terminal/app in System Settings > Privacy & Security "
                "> Input Monitoring, then restart the terminal and try again."
            )

        ready = threading.Event()

        def _run():
            self._run_loop = Quartz.CFRunLoopGetCurrent()
            self._run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
            Quartz.CFRunLoopAddSource(self._run_loop, self._run_loop_source, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(self._tap, True)
            ready.set()
            Quartz.CFRunLoopRun()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        ready.wait(timeout=2)

    def stop(self) -> None:
        if self._run_loop is not None:
            Quartz.CFRunLoopStop(self._run_loop)
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._tap = None
        self._run_loop = None
        self._run_loop_source = None
        self._thread = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_macos_capture.py -v`
Expected: 6 passed (on macOS; skipped elsewhere). The permission-error test passes for real right now — this machine has not granted Input Monitoring to this terminal yet, so it genuinely exercises the denied path, not a mock.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml capt/record/macos_capture.py tests/test_macos_capture.py
git commit -m "Add macOS global click/keystroke capture with hotkey marking"
```

**Note for later manual verification (not part of this task's automated tests):** once Input Monitoring is granted to your terminal app, `test_global_capture_start_raises_permission_error_without_input_monitoring` will start *failing* (no exception raised) — that's expected and correct; at that point replace it with a manual check that `start()`/`stop()` run cleanly, since an automated test can't grant/revoke a real macOS permission mid-run.

---

### Task 4: `run_beat()` core orchestration

**Files:**
- Create: `capt/record/beat.py`
- Test: `tests/test_beat.py`

**Interfaces:**
- Consumes: `capt.record.steps.drive_steps` (Task 2), `capt.record.macos_capture.GlobalCapture` (Task 3, imported lazily), `capt.zoom.{create_tracker, build_zoom_segments, merge_zoom_segments}`, `capt.config.{read_config, write_config}`, `capt.export.{cap_bin, export}` (all existing, unchanged).
- Produces: `BeatResult` dataclass (`recording_id: str, cap_path: str, events: list, zoom_segments: list, export_path: str | None`), `run_beat(url, steps, out_dir, name="full", screen_id=None, marker_source="steps", zoom_amount=2.0, export_to=None) -> BeatResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_beat.py
from unittest.mock import MagicMock, patch

import pytest

from capt.record.beat import BeatResult, run_beat


def _patch_all(**overrides):
    """Patch every external call run_beat makes; override specific ones per test."""
    defaults = dict(
        _start_recording=MagicMock(return_value={"recordingId": "rec-1", "path": "/tmp/full.cap"}),
        _stop_recording=MagicMock(return_value={"recordingMetaExists": True}),
        _validate_project=MagicMock(return_value={"valid": True}),
        drive_steps=MagicMock(),
        read_config=MagicMock(return_value={"timeline": {"zoomSegments": []}}),
        write_config=MagicMock(),
        cap_export=MagicMock(return_value={"path": "/tmp/out.mp4"}),
    )
    defaults.update(overrides)
    patches = [
        patch("capt.record.beat._start_recording", defaults["_start_recording"]),
        patch("capt.record.beat._stop_recording", defaults["_stop_recording"]),
        patch("capt.record.beat._validate_project", defaults["_validate_project"]),
        patch("capt.record.steps.drive_steps", defaults["drive_steps"]),
        patch("capt.record.beat.read_config", defaults["read_config"]),
        patch("capt.record.beat.write_config", defaults["write_config"]),
        patch("capt.record.beat.cap_export", defaults["cap_export"]),
    ]
    return patches, defaults


def test_run_beat_happy_path_returns_beat_result(tmp_path):
    patches, mocks = _patch_all()
    for p in patches:
        p.start()
    try:
        result = run_beat(
            url="https://example.com",
            steps=[{"action": "click", "selector": "#go"}],
            out_dir=str(tmp_path),
            name="full",
        )
    finally:
        for p in patches:
            p.stop()

    assert isinstance(result, BeatResult)
    assert result.recording_id == "rec-1"
    assert result.cap_path == str(tmp_path / "full.cap")
    assert result.export_path is None
    mocks["drive_steps"].assert_called_once()
    mocks["_stop_recording"].assert_called_once_with("rec-1")
    mocks["write_config"].assert_called_once()


def test_run_beat_stops_recording_even_if_driving_raises(tmp_path):
    patches, mocks = _patch_all(drive_steps=MagicMock(side_effect=RuntimeError("boom")))
    for p in patches:
        p.start()
    try:
        with pytest.raises(RuntimeError, match="boom"):
            run_beat(url="https://example.com", steps=[], out_dir=str(tmp_path))
    finally:
        for p in patches:
            p.stop()

    mocks["_stop_recording"].assert_called_once_with("rec-1")


def test_run_beat_continues_to_export_if_zoom_merge_fails(tmp_path, capsys):
    patches, mocks = _patch_all(read_config=MagicMock(side_effect=RuntimeError("cap not reachable")))
    for p in patches:
        p.start()
    try:
        result = run_beat(
            url="https://example.com", steps=[], out_dir=str(tmp_path),
            export_to=str(tmp_path / "out.mp4"),
        )
    finally:
        for p in patches:
            p.stop()

    mocks["write_config"].assert_not_called()
    mocks["cap_export"].assert_called_once()
    assert result.export_path == "/tmp/out.mp4"
    assert "continuing without it" in capsys.readouterr().out


def test_run_beat_does_not_export_when_export_to_is_none(tmp_path):
    patches, mocks = _patch_all()
    for p in patches:
        p.start()
    try:
        result = run_beat(url="https://example.com", steps=[], out_dir=str(tmp_path))
    finally:
        for p in patches:
            p.stop()

    mocks["cap_export"].assert_not_called()
    assert result.export_path is None


def test_run_beat_global_capture_starts_and_stops_capture(tmp_path):
    patches, mocks = _patch_all()
    fake_capture = MagicMock()
    with patch("capt.record.macos_capture.GlobalCapture", return_value=fake_capture) as gc_cls:
        for p in patches:
            p.start()
        try:
            run_beat(
                url=None, steps=[], out_dir=str(tmp_path),
                marker_source="global-capture",
            )
        finally:
            for p in patches:
                p.stop()

    gc_cls.assert_called_once()
    fake_capture.start.assert_called_once()
    fake_capture.stop.assert_called_once()


def test_run_beat_skips_driving_when_no_url_and_steps_marker_source(tmp_path):
    patches, mocks = _patch_all()
    for p in patches:
        p.start()
    try:
        run_beat(url=None, steps=[], out_dir=str(tmp_path), marker_source="steps")
    finally:
        for p in patches:
            p.stop()

    mocks["drive_steps"].assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_beat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capt.record.beat'`

- [ ] **Step 3: Implement `beat.py`**

```python
# capt/record/beat.py
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
    """Run `cap <args> --json` and parse the single-line JSON response.

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
    try:
        return json.loads(out.splitlines()[-1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"cap {' '.join(args)} returned unparseable output: {out!r}") from e


def _start_recording(cap_path: str, screen_id: Optional[str]) -> dict:
    args = ["record", "start", "--detach", "--path", cap_path]
    if screen_id:
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
    """
    from capt.record.steps import drive_steps

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    cap_path = str(out_path / f"{name}.cap")

    tracker = create_tracker()
    sources = marker_source.split("+")

    capture = None
    if "global-capture" in sources:
        from capt.record.macos_capture import GlobalCapture
        capture = GlobalCapture(tracker)
        capture.start()

    started = _start_recording(cap_path, screen_id)
    recording_id = started["recordingId"]

    try:
        if "steps" in sources and (url or steps):
            drive_steps(url, steps, tracker)
    finally:
        if capture is not None:
            capture.stop()
        _stop_recording(recording_id)

    _validate_project(cap_path)

    events = tracker.events()
    zoom_segments = build_zoom_segments(events, amount=zoom_amount)
    try:
        current = read_config(cap_path)
        merged = merge_zoom_segments(current, zoom_segments)
        write_config(cap_path, merged)
    except Exception as e:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_beat.py -v`
Expected: 6 passed

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `uv run pytest tests/ -v`
Expected: all tests pass (existing `tests/test_zoom.py`'s 10, plus everything from Tasks 1–4)

- [ ] **Step 6: Commit**

```bash
git add capt/record/beat.py tests/test_beat.py
git commit -m "Add run_beat(): shared OS-agnostic beat cycle"
```

---

### Task 5: Preflight dispatcher split

**Files:**
- Create: `capt/preflight_windows.py`
- Create: `capt/preflight_macos.py`
- Modify: `capt/preflight.py`
- Test: `tests/test_preflight.py`

**Interfaces:**
- Produces: `capt/preflight_windows.py::gate_powershell_reachable() -> tuple[bool, str]`; `capt/preflight_macos.py::gate_global_capture_permission() -> tuple[bool, str]`; `capt/preflight.py::preflight(url=None, output_dir="recordings", require_playwright=True, marker_source="steps") -> bool` (same common gates as today, plus a platform-dispatched gate appended: PowerShell on Windows/WSL, global-capture permission on macOS when `marker_source` includes `"global-capture"`).

Only G6 (PowerShell reachable) is actually Windows-specific in the current `capt/preflight.py` — G1–G5 and G7 (Tailscale) are already platform-agnostic and stay in `preflight.py` unchanged. This task narrows the split to what's real rather than what the design doc's shorthand implied.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_preflight.py
from unittest.mock import MagicMock, patch

from capt.preflight_windows import gate_powershell_reachable


def test_gate_powershell_reachable_true_when_echo_succeeds():
    fake_proc = MagicMock(stdout="ok\n")
    with patch("subprocess.run", return_value=fake_proc):
        passed, message = gate_powershell_reachable()
    assert passed is True
    assert "PowerShell reachable" in message


def test_gate_powershell_reachable_false_on_exception():
    with patch("subprocess.run", side_effect=FileNotFoundError("no powershell.exe")):
        passed, message = gate_powershell_reachable()
    assert passed is False
    assert "NOT reachable" in message
```

```python
# tests/test_preflight_macos.py
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only module")

from unittest.mock import MagicMock, patch

from capt.preflight_macos import gate_global_capture_permission


def test_gate_global_capture_permission_false_without_input_monitoring():
    # Real, not mocked — this terminal has not been granted Input Monitoring.
    passed, message = gate_global_capture_permission()
    assert passed is False
    assert "Input Monitoring" in message


def test_gate_global_capture_permission_true_when_capture_starts_cleanly():
    fake_capture = MagicMock()
    with patch("capt.preflight_macos.GlobalCapture", return_value=fake_capture):
        passed, message = gate_global_capture_permission()
    assert passed is True
    fake_capture.start.assert_called_once()
    fake_capture.stop.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_preflight.py tests/test_preflight_macos.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the two new modules**

```python
# capt/preflight_windows.py
"""Windows/WSL-only preflight gate: is PowerShell reachable from WSL?

Extracted from capt/preflight.py's inline G6 check so it's independently
testable and only invoked on the platform it applies to.
"""

import subprocess


def gate_powershell_reachable() -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "echo ok"],
            capture_output=True, text=True, timeout=10,
        )
        if "ok" in proc.stdout.lower():
            return True, "PowerShell reachable"
        return False, "PowerShell reachable but did not echo back 'ok'"
    except Exception as e:
        return False, f"PowerShell NOT reachable: {e}"
```

```python
# capt/preflight_macos.py
"""macOS-only preflight gate: is the Input Monitoring permission granted for
global-capture marker collection?

Reuses GlobalCapture itself (start/stop) rather than a separate permission
query API, since CGEventTapCreate returning None IS the permission-denied
signal — no second API to get wrong.
"""

from capt.record.macos_capture import GlobalCapture


def gate_global_capture_permission() -> tuple[bool, str]:
    capture = GlobalCapture(tracker=None)
    try:
        capture.start()
    except PermissionError as e:
        return False, str(e)
    else:
        capture.stop()
        return True, "Input Monitoring granted (global-capture available)"
```

- [ ] **Step 4: Wire the dispatch into `capt/preflight.py`**

Modify `capt/preflight.py`: remove the inline G6 PowerShell block (lines 155–161 in the current file) and the `_powershell_ok` helper (lines 58–67), replacing them with a platform dispatch at the end of the gate list. Full replacement of the `preflight()` function body from `# G6: PowerShell reachable` through the end of `# G7: Tailscale...` block:

```python
    # G6: platform-specific gate — PowerShell on Windows/WSL, global-capture
    # permission on macOS (only when that marker source is requested).
    import platform as _platform

    def _is_wsl() -> bool:
        try:
            return "microsoft" in open("/proc/version").read().lower()
        except OSError:
            return False

    if _platform.system() == "Windows" or _is_wsl():
        from capt.preflight_windows import gate_powershell_reachable
        passed, message = gate_powershell_reachable()
        print(f"  {'✓' if passed else '✗'} G6 {message}")
        gates.append(passed)
    elif _platform.system() == "Darwin" and "global-capture" in marker_source.split("+"):
        from capt.preflight_macos import gate_global_capture_permission
        passed, message = gate_global_capture_permission()
        print(f"  {'✓' if passed else '✗'} G6 {message}")
        gates.append(passed)
    else:
        print("  - G6 skipped (not applicable on this platform/marker source)")
        gates.append(True)

    # G7: Tailscale (only required for HTTPS targets)
    needs_https = bool(url) and url.lower().startswith("https://")
    if needs_https:
        if tailscale.is_running():
            name = tailscale.magic_dns_name()
            print(f"  ✓ G7 Tailscale up  ({name})")
            gates.append(True)
        elif tailscale.is_available():
            print("  ✗ G7 Tailscale installed but not running (HTTPS target needs it)")
            gates.append(False)
        else:
            print("  ✗ G7 Tailscale not installed (HTTPS target needs it)")
            gates.append(False)
    else:
        print("  - G7 Tailscale skipped (HTTP target — not needed)")
        gates.append(True)
```

Also update the `preflight()` signature to accept the new parameter, and remove the now-unused `_powershell_ok` function and its `import` of nothing extra (it only used `subprocess`, which stays imported for `_cap_json`):

```python
def preflight(
    url: Optional[str] = None,
    output_dir: str = "recordings",
    require_playwright: bool = True,
    marker_source: str = "steps",
) -> bool:
```

Remove the old `require_beat_runner: bool = True` parameter — nothing in the current gate list actually used it (grep confirms no reference to `require_beat_runner` inside the function body), so it was dead. Update `capt/preflight.py`'s own `main()` to not pass it (it doesn't today either, so no change needed there).

- [ ] **Step 5: Wire `marker_source` through the `capt preflight` CLI command**

Without this, `capt preflight` standalone would never actually request the new macOS gate — it would silently default to `"steps"` and skip it. Replace the `preflight` command in `capt/cli.py` (currently `capt/cli.py:212-223`):

```python
@main.command()
@click.argument("url", required=False)
@click.option("--output-dir", default="recordings")
@click.option("--skip-playwright", is_flag=True)
@click.option("--marker-source", default="steps",
              type=click.Choice(["steps", "global-capture", "steps+global-capture"]),
              help="Include the global-capture permission gate (macOS-only)")
@click.option("--json", "json_out", is_flag=True)
def preflight(url, output_dir, skip_playwright, marker_source, json_out):
    """Check all dependencies before recording."""
    from capt.preflight import preflight as run_preflight
    ok = run_preflight(url, output_dir, require_playwright=not skip_playwright,
                       marker_source=marker_source)
    if json_out:
        click.echo(json.dumps({"ok": ok}))
    sys.exit(0 if ok else 1)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_preflight.py tests/test_preflight_macos.py -v`
Expected: 4 passed (2 on any platform, 2 macOS-only — the permission-denied one passes for real here)

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add capt/preflight.py capt/preflight_windows.py capt/preflight_macos.py capt/cli.py tests/test_preflight.py tests/test_preflight_macos.py
git commit -m "Split preflight into platform-dispatched gates, wire marker-source through CLI, drop dead require_beat_runner param"
```

---

### Task 6: Extract `capt/guide/pipeline.py::run_guide()`

**Files:**
- Create: `capt/guide/pipeline.py`
- Modify: `capt/cli.py:93-172` (the `guide` command)
- Test: `tests/test_guide_pipeline.py`

**Interfaces:**
- Consumes: `capt.guide.ingest.ingest`, `capt.guide.render.render`, `capt.guide.structure.structure`, `capt.guide.transcribe.transcribe` (all existing, unchanged).
- Produces: `run_guide(cap_path: str, out_dir: str, ai: bool = False, transcript_path: str | None = None, model: str | None = None, fmt: str = "both") -> dict` returning `{"path": out_dir, "steps": int, "html": str | None, "md": str | None}`.

This extraction also fixes a real bug found while verifying this plan: today's inline code in `cli.py`'s `guide` command calls `transcribe(str(audio), out_path=str(t_out))`, but `transcribe()` has no `out_path` parameter (confirmed by reading `capt/guide/transcribe.py`) — this raises `TypeError` any time `capt guide --ai` hits the fallback-transcribe branch (an external `--transcript` not given, but `audio-input.ogg` present). `run_guide()` fixes this by calling `transcribe()` for its return value and writing it out manually, matching `transcribe.py`'s own `main()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_guide_pipeline.py
import json
from unittest.mock import MagicMock, patch

from capt.guide.pipeline import run_guide


def test_run_guide_deterministic_path_ingests_and_renders(tmp_path):
    cap_dir = tmp_path / "full.cap"
    cap_dir.mkdir()
    (cap_dir / "display.mp4").write_bytes(b"")
    out_dir = tmp_path / "out"

    fake_ingest = MagicMock(return_value={"title": "T", "step_count": 3})
    fake_render = MagicMock(return_value={"html": "out/guide.html", "md": None})

    with patch("capt.guide.ingest.ingest", fake_ingest), \
         patch("capt.guide.render.render", fake_render):
        result = run_guide(str(cap_dir), str(out_dir))

    fake_ingest.assert_called_once_with(str(cap_dir), str(out_dir), transcript_path=None)
    assert result == {"path": str(out_dir), "steps": 3, "html": "out/guide.html", "md": None}


def test_run_guide_ai_path_transcribes_and_structures_without_out_path_kwarg(tmp_path):
    # Regression test for the TypeError bug: transcribe() takes no out_path
    # kwarg. run_guide must call it with just audio_path and write the
    # result itself.
    cap_dir = tmp_path / "full.cap"
    cap_dir.mkdir()
    (cap_dir / "display.mp4").write_bytes(b"")
    (cap_dir / "audio-input.ogg").write_bytes(b"")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    fake_ingest = MagicMock(return_value={"title": "T", "step_count": 1})
    fake_transcribe = MagicMock(return_value={"duration": 1.0, "text": "hi", "segments": []})
    fake_structure = MagicMock(return_value={})
    fake_render = MagicMock(return_value={"html": "out/guide.html", "md": "out/guide.md"})

    with patch("capt.guide.ingest.ingest", fake_ingest), \
         patch("capt.guide.transcribe.transcribe", fake_transcribe), \
         patch("capt.guide.structure.structure", fake_structure), \
         patch("capt.guide.render.render", fake_render):
        run_guide(str(cap_dir), str(out_dir), ai=True)

    fake_transcribe.assert_called_once_with(str(cap_dir / "audio-input.ogg"))
    written = json.loads((out_dir / "transcript.json").read_text())
    assert written["text"] == "hi"
    fake_structure.assert_called_once()


def test_run_guide_ai_path_uses_given_transcript_path_without_transcribing(tmp_path):
    cap_dir = tmp_path / "full.cap"
    cap_dir.mkdir()
    (cap_dir / "display.mp4").write_bytes(b"")
    out_dir = tmp_path / "out"
    transcript = tmp_path / "given.json"
    transcript.write_text(json.dumps({"segments": []}))

    fake_ingest = MagicMock(return_value={"title": "T", "step_count": 1})
    fake_transcribe = MagicMock()
    fake_structure = MagicMock(return_value={})
    fake_render = MagicMock(return_value={"html": "out/guide.html", "md": None})

    with patch("capt.guide.ingest.ingest", fake_ingest), \
         patch("capt.guide.transcribe.transcribe", fake_transcribe), \
         patch("capt.guide.structure.structure", fake_structure), \
         patch("capt.guide.render.render", fake_render):
        run_guide(str(cap_dir), str(out_dir), ai=True, transcript_path=str(transcript))

    fake_transcribe.assert_not_called()
    fake_structure.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_guide_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'capt.guide.pipeline'`

- [ ] **Step 3: Implement `run_guide()`**

```python
# capt/guide/pipeline.py
"""Reusable guide-generation pipeline: ingest -> (transcribe) -> (structure)
-> render. Extracted from capt/cli.py's `guide` command so both the CLI and
a future chained command (Phase 3's `capt walkthrough`) can call one function
instead of duplicating this sequencing.
"""

import json
from pathlib import Path
from typing import Optional


def run_guide(
    cap_path: str,
    out_dir: str,
    ai: bool = False,
    transcript_path: Optional[str] = None,
    model: Optional[str] = None,
    fmt: str = "both",
) -> dict:
    """Run the guide pipeline against a .cap project.

    Deterministic by default (ingest + render only). With ai=True, also
    transcribes (if no transcript_path given and audio-input.ogg exists) and
    runs the structure pass before rendering.

    Returns {"path": out_dir, "steps": int, "html": str | None, "md": str | None}.
    """
    from capt.guide.ingest import ingest
    from capt.guide.render import render

    cap_dir = Path(cap_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    result = ingest(str(cap_dir), out_dir, transcript_path=transcript_path)

    if ai:
        from capt.guide.structure import structure
        from capt.guide.transcribe import transcribe

        resolved_transcript = transcript_path
        if not resolved_transcript:
            audio = cap_dir / "audio-input.ogg"
            if audio.exists():
                transcript_data = transcribe(str(audio))
                t_out = Path(out_dir) / "transcript.json"
                t_out.write_text(json.dumps(transcript_data, indent=2, ensure_ascii=False))
                resolved_transcript = str(t_out)

        if resolved_transcript:
            items_out = Path(out_dir) / "items.json"
            structure(resolved_transcript, str(items_out), model=model,
                     title=result["title"], recording=result["title"])

    display = cap_dir / "display.mp4"
    if not display.exists():
        meta = json.loads((cap_dir / "recording-meta.json").read_text())
        segs = meta.get("segments", [])
        if segs and "display" in segs[0]:
            display = cap_dir / segs[0]["display"]["path"]
        elif "display" in meta:
            display = cap_dir / meta["display"]["path"]

    items_path = Path(out_dir) / "items.json"
    if items_path.exists():
        render_result = render(str(items_path), str(display), out_dir, fmt=fmt)
    else:
        render_result = {"html": str(Path(out_dir) / "guide.html"), "md": None}

    return {
        "path": out_dir,
        "steps": result["step_count"],
        "html": render_result.get("html"),
        "md": render_result.get("md"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_guide_pipeline.py -v`
Expected: 3 passed

- [ ] **Step 5: Point `cli.py`'s `guide` command at `run_guide()`**

Replace `capt/cli.py:102-172` (the entire body of the `guide` command after its docstring) with:

```python
def guide(project_path, ai, fmt, out, transcript, model, json_out):
    """Turn a .cap recording into an illustrated step-by-step guide.

    Pipeline: ingest → (transcribe) → (structure if --ai) → render.
    Deterministic by default; --ai enables LLM step-text generation.
    """
    from capt.guide.pipeline import run_guide

    cap_path = Path(project_path)
    out_dir = out or f"output/{cap_path.stem}"

    if json_out:
        click.echo(json.dumps({"type": "Progress", "stage": "guide"}))

    result = run_guide(str(cap_path), out_dir, ai=ai, transcript_path=transcript,
                       model=model, fmt=fmt)

    if json_out:
        click.echo(json.dumps({"type": "Completed", **result}))
    else:
        click.echo(f"✓ Guide: {result['steps']} steps -> {result['path']}")
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add capt/guide/pipeline.py capt/cli.py tests/test_guide_pipeline.py
git commit -m "Extract run_guide() from cli.py, fix transcribe() out_path TypeError bug"
```

---

### Task 7: Wire `capt/cli.py`'s `record` command to branch by platform

**Files:**
- Modify: `capt/cli.py:1-89` (imports and the `record` command)
- Test: `tests/test_cli_record.py`

**Interfaces:**
- Consumes: `capt.record.beat.run_beat` (Task 4).
- Produces: `_is_wsl() -> bool` (in `capt/cli.py`), modified `record` CLI command with new `--steps`, `--marker-source`, `--export-to` options.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_record.py
import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from capt.cli import main
from capt.record.beat import BeatResult


def test_record_calls_run_beat_in_process_when_not_wsl(tmp_path):
    fake_result = BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "full.cap"),
        events=[], zoom_segments=[], export_path=None,
    )
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("capt.record.beat.run_beat", return_value=fake_result) as run_beat_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path), "--json"])

    assert result.exit_code == 0
    run_beat_mock.assert_called_once()
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["recordingId"] == "rec-1"
    assert payload["capPath"] == str(tmp_path / "full.cap")


def test_record_uses_powershell_hop_when_wsl(tmp_path):
    fake_proc = MagicMock(returncode=0, stdout='{"recordingId": "rec-1", "capProjectPath": "full.cap"}\n')
    with patch("capt.cli._is_wsl", return_value=True), \
         patch("subprocess.run", return_value=fake_proc) as run_mock:
        runner = CliRunner()
        result = runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path), "--json"])

    assert result.exit_code == 0
    run_mock.assert_called_once()
    assert "powershell.exe" in run_mock.call_args[0][0]


def test_record_reads_steps_json_file(tmp_path):
    steps_file = tmp_path / "steps.json"
    steps_file.write_text(json.dumps([{"action": "click", "selector": "#go"}]))
    fake_result = BeatResult(
        recording_id="rec-1", cap_path=str(tmp_path / "full.cap"),
        events=[], zoom_segments=[], export_path=None,
    )
    with patch("capt.cli._is_wsl", return_value=False), \
         patch("capt.record.beat.run_beat", return_value=fake_result) as run_beat_mock:
        runner = CliRunner()
        runner.invoke(main, ["record", "https://example.com", "--out", str(tmp_path),
                             "--steps", str(steps_file)])

    called_steps = run_beat_mock.call_args.kwargs.get("steps", run_beat_mock.call_args[0][1] if len(run_beat_mock.call_args[0]) > 1 else None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_record.py -v`
Expected: FAIL — `_is_wsl` doesn't exist yet / current `record` command doesn't accept `--steps`/`--marker-source`

- [ ] **Step 3: Replace the `record` command in `capt/cli.py`**

Add near the top of `capt/cli.py` (after the existing imports):

```python
def _is_wsl() -> bool:
    """True when running inside WSL (Windows Subsystem for Linux)."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False
```

Replace the entire `record` command (`capt/cli.py:27-88`) with:

```python
@main.command()
@click.argument("url", required=False)
@click.option("--beat", "name", default="full", help="Named beat to record")
@click.option("--out", default="recordings", help="Output directory")
@click.option("--screen", default=None, help="Cap screen ID")
@click.option("--steps", default=None, help="Path to a steps.json file (scripted actions)")
@click.option("--marker-source", default="steps",
              type=click.Choice(["steps", "global-capture", "steps+global-capture"]),
              help="How to collect zoom markers (global-capture is macOS-only)")
@click.option("--export-to", default=None, help="Also export the recording to this MP4 path")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def record(url, name, out, screen, steps, marker_source, export_to, json_out):
    """Automate a browser-driven screen recording with automatic zoom.

    On macOS/Linux, runs in-process (no PowerShell hop). On WSL, invokes the
    beat-runner on Windows via PowerShell, unchanged from before.
    """
    step_list = []
    if steps:
        step_list = json.loads(Path(steps).read_text())

    if _is_wsl():
        _record_via_windows(url, name, out, screen, json_out)
        return

    from capt.record.beat import run_beat
    from dataclasses import asdict

    if json_out:
        click.echo(json.dumps({"type": "Progress", "stage": "recording"}))

    result = run_beat(url, step_list, out, name=name, screen_id=screen,
                      marker_source=marker_source, export_to=export_to)

    if json_out:
        click.echo(json.dumps({
            "type": "Completed",
            "recordingId": result.recording_id,
            "capPath": result.cap_path,
            "events": result.events,
            "zoomSegments": result.zoom_segments,
            "exportPath": result.export_path,
        }))
    else:
        click.echo(f"✓ Beat '{name}' recorded: {result.cap_path}")
        if result.export_path:
            click.echo(f"  Exported: {result.export_path}")


def _record_via_windows(url, name, out, screen, json_out):
    """WSL -> PowerShell -> Windows beat_runner_entry.py, unchanged in spirit
    from the pre-macOS-support implementation."""
    from capt import tailscale

    out_dir = str(Path(out).resolve())
    if url and url.lower().startswith("https://"):
        resolved = tailscale.resolve_target(url)
        if resolved != url:
            if not json_out:
                click.echo(f"→ HTTPS target via Tailscale: {resolved}")
            url = resolved

    ps_cmd = f"cd C:\\cap-tools; python beat_runner_entry.py {name} {url} {out_dir}"
    if screen:
        ps_cmd += f" --screen {screen}"

    if json_out:
        click.echo(json.dumps({"status": "running", "beat": name, "url": url}))

    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=600,
    )

    if proc.returncode != 0:
        err = proc.stderr.strip() or "beat runner failed"
        if json_out:
            click.echo(json.dumps({"status": "error", "error": err}))
        else:
            click.echo(f"✗ {err}", err=True)
        sys.exit(1)

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        result = {"raw": proc.stdout.strip()}

    if json_out:
        result["status"] = "completed"
        click.echo(json.dumps(result))
    else:
        click.echo(f"✓ Beat '{name}' recorded: {result.get('capProjectPath', '?')}")
```

Add `import subprocess` to the top-level imports of `capt/cli.py` (it was previously only imported inside the `record` function body — now `_record_via_windows` needs it at module scope so the test can patch `subprocess.run`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_record.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add capt/cli.py tests/test_cli_record.py
git commit -m "Branch capt record by platform: in-process run_beat on macOS/Linux, PowerShell hop stays on WSL"
```

---

### Task 8: Windows-side shim, vendoring, and archiving the old runner

**Files:**
- Create: `win/beat_runner_entry.py`
- Create: `win/_archive/` (move `win/beat_runner.py` here)
- Modify: `win/install.ps1`

**Interfaces:**
- Consumes: `capt.record.beat.run_beat` (vendored onto Windows by the updated `install.ps1`).
- Produces: `win/beat_runner_entry.py`'s CLI surface: `python beat_runner_entry.py <name> <url> <out_dir> [--screen ID] [--steps FILE] [--marker-source ...] [--export-to PATH]`, printing one JSON line (`json.dumps(asdict(result))`) to stdout — this is what `capt/cli.py::_record_via_windows` parses via `proc.stdout.strip().splitlines()[-1]`.

This task cannot be tested from this machine — there is no Windows box here. Steps 1–3 are file changes verified only for syntactic correctness (`python -m py_compile`); the real verification is a manual step the user runs on their own WSL/Windows setup, called out explicitly at the end.

- [ ] **Step 1: Archive the old runner**

```bash
mkdir -p win/_archive
git mv win/beat_runner.py win/_archive/beat_runner.py
```

- [ ] **Step 2: Create the thin entry-point shim**

```python
# win/beat_runner_entry.py
"""Windows-side entry point for `capt record` invoked from WSL over
PowerShell. Thin shim: parses argv, calls the shared, vendored
capt.record.beat.run_beat(), prints the result as one JSON line for WSL to
read from stdout.

This file plus a full copy of the capt/ package are what live at
C:\\cap-tools\\ after running win/install.ps1 — see
docs/superpowers/specs/2026-07-30-macos-record-support-design.md.
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("url", nargs="?", default=None)
    ap.add_argument("out_dir")
    ap.add_argument("--screen", default=None)
    ap.add_argument("--steps", default=None)
    ap.add_argument("--marker-source", default="steps")
    ap.add_argument("--export-to", default=None)
    args = ap.parse_args()

    from capt.record.beat import run_beat

    step_list = []
    if args.steps:
        step_list = json.loads(Path(args.steps).read_text())

    result = run_beat(
        args.url, step_list, args.out_dir, name=args.name,
        screen_id=args.screen, marker_source=args.marker_source,
        export_to=args.export_to,
    )
    print(json.dumps(asdict(result)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify it at least compiles**

Run: `cd /Users/kylebrodeur/workspace/cap-tools && python3 -m py_compile win/beat_runner_entry.py`
Expected: no output, exit code 0 (this only checks syntax — it cannot run for real without Playwright/`cap` on this machine, and this machine isn't Windows anyway)

- [ ] **Step 4: Update `win/install.ps1` to vendor `capt`**

Replace `win/install.ps1`'s contents:

```powershell
# One-time Windows setup for cap-tools beat runner
# Run from Windows PowerShell (admin not required):
#   powershell -File install.ps1

Write-Host "Installing cap-tools beat runner dependencies..."
pip install -r requirements.txt
python -m playwright install chromium

Write-Host "Installing capt package (editable) so beat_runner_entry.py can import capt.record.beat..."
$repoRoot = Split-Path $PSScriptRoot -Parent
pip install -e $repoRoot

Write-Host "Done. Verify with: python beat_runner_entry.py --help"
```

- [ ] **Step 5: Commit**

```bash
git add win/beat_runner_entry.py win/install.ps1 win/_archive/beat_runner.py
git commit -m "Add Windows-side beat_runner_entry.py shim, vendor capt via pip install -e"
```

- [ ] **Step 6: Flag for manual verification — not part of this automated plan**

This step is a note, not something to run now: before relying on the Windows/WSL path again, run `win/install.ps1` on the actual Windows machine, then from WSL run `capt record <a test url> --out recordings --json` and confirm it produces a real `.cap` the same way it did before this change. This plan does not claim the Windows side works until that manual check is done — there is no Windows box available from this session to verify it here.

---

### Task 9: Real end-to-end verification on this Mac

**Files:**
- Modify: `docs/playbook-auto-zoom-recording.md` (update the commands it references to the new `capt record` surface)

This task is manual, not automated — it requires the Input Monitoring and Screen Recording permissions granted interactively, which no earlier task can do from a script.

- [ ] **Step 1: Update the playbook's commands**

In `docs/playbook-auto-zoom-recording.md`, replace the `capt zoom mark` / `capt zoom apply` two-step flow (steps 3 and 6 in that doc) with the new one-shot `capt record` flow, since `run_beat()` now does the marking and zoom-merge internally:

```bash
capt doctor --json   # (existing capt preflight steps 1 stay the same)
capt record https://example.com --out recordings --marker-source steps+global-capture --export-to test-walkthrough.mp4 --json
```

Note in the playbook that `--marker-source steps+global-capture` means: drive nothing automatically (no `--steps` given) but capture every real click/keystroke plus Cmd+Shift+M for labeled marks, while you do the walkthrough by hand — replacing the old manual `capt zoom mark` step entirely.

- [ ] **Step 2: Grant the permissions**

When you're ready to actually run it: System Settings → Privacy & Security → Input Monitoring → enable for your terminal app; System Settings → Privacy & Security → Screen Recording → enable for your terminal app (if not already granted for Cap Desktop specifically). Restart the terminal app after granting.

- [ ] **Step 3: Run it for real and check the result**

Run the command from Step 1, do a short walkthrough (a few real clicks), then open `test-walkthrough.mp4` and confirm zoom kicks in around each click, holds briefly, and the merged config didn't clobber anything already set in Studio (same checks as the original playbook's step 8).

- [ ] **Step 4: Commit the playbook update**

```bash
git add docs/playbook-auto-zoom-recording.md
git commit -m "Update playbook to the new one-shot capt record flow"
```

---

## Self-Review Notes

- **Spec coverage:** All of Phase 1's module layout (`capt/record/{beat,steps,macos_capture}.py`, `preflight_macos.py`/`preflight_windows.py`, `win/beat_runner_entry.py`, `win/install.ps1`, `capt/guide/pipeline.py`) is covered by Tasks 1–8. The groundwork section (`BeatResult` dataclass, `run_guide()` extraction) is Tasks 4 and 6. The real integration test and Windows-regression flag from the spec's testing plan are Task 9 and Task 8's final step, respectively. Phases 2 and 3 are out of scope for this plan, per the spec.
- **Correction from the spec's phrasing:** the spec described `preflight_windows.py` as extracting "PowerShell reachable, Windows beat-runner ready" — but no "beat-runner ready" gate exists in the current code (only `docs/ARCHITECTURE.md`'s older, superseded design mentioned one), and there's no `require_beat_runner` behavior actually implemented today. Task 5 extracts what's real (PowerShell reachable) and removes the unused `require_beat_runner` parameter rather than inventing a check nothing calls for.
- **Bug found and fixed in passing:** Task 6 fixes a real `TypeError` in the current `capt guide --ai` fallback-transcribe path (`transcribe()` called with a nonexistent `out_path` kwarg) — caught while verifying `run_guide()`'s extraction against the actual `transcribe()` signature, not a speculative addition.
- **Permission naming corrected from the spec:** the spec said "Accessibility permission" for global-capture; the actual macOS TCC category for `CGEventTapCreate`-based listening is **Input Monitoring**, a separate permission from Accessibility (which Phase 2/3's AXUIElement work will need). Tasks 3 and 5 use the correct name throughout.
