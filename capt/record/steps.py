"""Beat step schema (goto/click/fill/wait/mark) and the Playwright driver
that executes them against a live page, marking a shared event tracker as it
goes. See docs/superpowers/specs/2026-07-30-macos-record-support-design.md.

Every step is a BEAT: it has a label, a start time, and a verified outcome.
The driver records {label, elapsed_s, beat_s, ok, error} per beat so a take
can be checked for completeness (every beat ran and succeeded) and the
sidecar can drive per-beat section extraction downstream.
"""
from typing import Optional

from playwright.sync_api import sync_playwright

VALID_ACTIONS = {"goto", "click", "fill", "wait", "mark"}

DEFAULT_STEP_TIMEOUT_MS = 20_000

def validate_steps(steps: list) -> list:
    """Validate a list of step dicts, raising ValueError on the first problem.

    Schema:
        goto:  {"action": "goto", "url": str}
        click: {"action": "click", "selector": str, "count": int (optional, default 1)}
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



def _beat_label(step: dict, index: int) -> str:
    """Stable beat label: explicit label wins, else action+target."""
    action = step["action"]
    label = step.get("label")
    if label:
        return label
    if action == "goto":
        return f"goto:{step['url']}"
    if action == "click":
        return f"click:{step['selector']}"
    if action == "fill":
        return f"fill:{step['selector']}"
    return f"{action}-{index}"


def _do_step(page, step: dict, timeout_ms: int = DEFAULT_STEP_TIMEOUT_MS) -> None:
    """Run one step's action against the page. Raises on failure — never
    blocks forever: every Playwright call gets the beat timeout (per-step
    'timeout' overrides it), so a dead selector fails the take loudly
    instead of hanging the recording on dead air (the second-take flake)."""
    action = step["action"]
    t = step.get("timeout", timeout_ms)
    if action == "goto":
        page.goto(step["url"], timeout=t)
    elif action == "click":
        page.click(step["selector"], click_count=step.get("count", 1), timeout=t)
    elif action == "fill":
        page.fill(step["selector"], step["text"], timeout=t)
    elif action == "wait":
        if "selector" in step:
            page.wait_for_selector(step["selector"], timeout=t)
        elif "text" in step:
            page.wait_for_selector(f"text={step['text']}", timeout=t)
        elif "ms" in step:
            page.wait_for_timeout(step["ms"])


def run_beats(page, steps: list, tracker,
              timeout_ms: int = DEFAULT_STEP_TIMEOUT_MS) -> list:
    """Drive each step as a verified beat, in order.

    Every beat records THREE tracker marks:
      {label}:start, {label}:ok (or :fail) — plus returns a report list of
      {label, elapsed_s, beat_s, ok, error} where beat_s is the beat's own
      duration. A failed beat raises immediately (after recording :fail) so
      a take never continues in a silently broken state — the recording is
      still stopped and finalized by the caller's finally block.
    """
    import time as _time

    report = []
    for i, step in enumerate(steps):
        label = _beat_label(step, i)
        tracker.mark(f"{label}:start")
        t0 = _time.monotonic()
        ok, error = True, None
        try:
            _do_step(page, step, timeout_ms)
        except Exception as e:
            ok, error = False, f"{type(e).__name__}: {e}"
        beat_s = round(_time.monotonic() - t0, 3)
        tracker.mark(f"{label}:{'ok' if ok else 'fail'}")
        report.append({
            "index": i, "label": label, "action": step["action"],
            "elapsed_s": tracker.events()[-1]["elapsed_s"],
            "beat_s": beat_s, "ok": ok, "error": error,
        })
        if not ok:
            raise RuntimeError(f"beat {i} ({label}) failed: {error}")
    return report


_VISIBLE_ACTIONS = {"goto", "click", "fill"}  # need an actual page on screen; wait/mark don't


def _needs_visible_browser(url, steps: list) -> bool:
    """True if anything here actually needs a real, visible page — a `url`
    to load, or a step that navigates/interacts with one. Pure wait/mark
    steps (e.g. just holding a recording open while narrating over some
    other window) don't, so there's no reason to pop up an empty, unused
    Chromium window in the middle of a take."""
    if url:
        return True
    return any(step.get("action") in _VISIBLE_ACTIONS for step in steps)


def _browser_context_args(storage_state, user_data_dir) -> dict:
    """Which auth mechanism the browser launch should use, if any.

    user_data_dir wins when both are given — a persistent profile covers
    everything a bare storageState JSON does, plus IndexedDB/service
    workers/PWA state.
    """
    if user_data_dir:
        return {"user_data_dir": user_data_dir}
    if storage_state:
        return {"storage_state": storage_state}
    return {}


def drive_steps(url, steps: list, tracker,
                storage_state: Optional[str] = None,
                user_data_dir: Optional[str] = None,
                cdp_endpoint: Optional[str] = None,
                timeout_ms: int = DEFAULT_STEP_TIMEOUT_MS) -> list:
    """Launch Playwright Chromium, optionally navigate to url, then drive
    each step as a VERIFIED beat in order (see run_beats).

    Returns the beat report: a list of {index, label, action, elapsed_s,
    beat_s, ok, error} — one entry per step, elapsed_s relative to the
    tracker's recording-anchored clock. Raises RuntimeError on the first
    failed beat (the take is broken; let the caller's finally finalize it).

    storage_state: path to a Playwright storageState JSON — cookies +
    localStorage from a previous authenticated session, applied to a
    fresh context. user_data_dir: path to a full Chrome/Chromium profile
    directory — launches a persistent context instead, so logins beyond
    cookies (service workers, IndexedDB, PWA installs) carry over;
    wins when both are given.

    Runs headless when nothing here needs a visible page (see
    _needs_visible_browser) — otherwise headed, since the point is usually
    to have Cap's recording show real page content.

    Always closes the browser, even if a step raises.
    """
    validate_steps(steps)
    headless = not _needs_visible_browser(url, steps)
    auth = _browser_context_args(storage_state, user_data_dir)
    with sync_playwright() as p:
        if cdp_endpoint:
            # Attach to an ALREADY-RUNNING browser (e.g. the installed PWA
            # launched with --remote-debugging-port) and drive it in place —
            # the recording captures the real app shell, not a synthetic
            # Chromium window.
            browser = p.chromium.connect_over_cdp(cdp_endpoint)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
        elif auth.get("user_data_dir"):
            context = p.chromium.launch_persistent_context(
                auth["user_data_dir"], headless=headless)
            browser, page = None, context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(**{
                k: v for k, v in auth.items() if k != "user_data_dir"})
            page = context.new_page()
        try:
            report = []
            if url:
                page.goto(url)
                tracker.mark("page-load")
            report = run_beats(page, steps, tracker, timeout_ms=timeout_ms)
            return report
        finally:
            if cdp_endpoint:
                # Attached to a live browser — disconnect, never close the
                # user's actual PWA/Chrome instance.
                if browser is not None:
                    browser.close()  # disconnect only — host browser keeps running
            elif browser is not None:
                browser.close()
            else:
                context.close()
