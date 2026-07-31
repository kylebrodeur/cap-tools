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


def drive_steps(url, steps: list, tracker) -> None:
    """Launch Playwright Chromium, optionally navigate to url, then drive
    each step in order, marking `tracker` as described in `_run_step`.

    Runs headless when nothing here needs a visible page (see
    _needs_visible_browser) — otherwise headed, since the point is usually
    to have Cap's recording show real page content.

    Always closes the browser, even if a step raises.
    """
    validate_steps(steps)
    headless = not _needs_visible_browser(url, steps)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            if url:
                page.goto(url)
                tracker.mark("page-load")
            for step in steps:
                _run_step(page, step, tracker)
        finally:
            browser.close()
