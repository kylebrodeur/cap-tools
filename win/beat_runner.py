"""Windows-side beat runner — Python Playwright + Cap recording.

Runs on Windows (invoked from WSL via PowerShell). Launches Chrome natively,
starts/stops Cap recording, drives UI beats, collects event timestamps.

Usage (from WSL):
    powershell.exe -NoProfile -Command "cd C:\\cap-tools; python beat_runner.py <beat> <url> <out-dir>"

Or directly on Windows:
    python beat_runner.py load http://wsl.localhost:7860 C:\\recordings
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
SCREEN_ID = "199517"          # default recording screen
FPS = 60
VIEWPORT_WIDTH = 1707
VIEWPORT_HEIGHT = 1067
CAP_BIN = "cap"               # cap-cli.exe should be on PATH


def _cap_start(screen_id: str, output_path: str) -> Optional[str]:
    """Start Cap recording in detached mode. Returns recordingId or None."""
    tmp = Path("C:\\temp\\cap-start-output.txt")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if tmp.exists():
        tmp.unlink()

    proc = subprocess.Popen(
        [CAP_BIN, "record", "start", "--screen", screen_id, "--fps", str(FPS),
         "--detach", "--json", "--path", output_path],
        stdout=open(str(tmp), "w"), stderr=subprocess.STDOUT,
    )
    time.sleep(3)

    try:
        data = tmp.read_text(encoding="utf-8")
        for line in data.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    obj = json.loads(line)
                    if "recordingId" in obj:
                        return obj["recordingId"]
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return None


def _cap_stop(recording_id: str) -> None:
    subprocess.run([CAP_BIN, "record", "stop", "--id", recording_id],
                   capture_output=True, timeout=60)


def _dismiss_overlays(page) -> None:
    """Remove common web overlays (cookie banners, headers)."""
    try:
        page.evaluate("""
            (() => {
                const hf = document.getElementById('huggingface-space-header');
                if (hf) { hf.style.display = 'none'; hf.remove(); }
                document.querySelectorAll('div, aside, section').forEach(el => {
                    const t = (el.innerText || '').toLowerCase();
                    if (/(cookie|accept|privacy)/.test(t) && t.length < 400) {
                        el.style.display = 'none'; el.remove();
                    }
                });
                document.querySelectorAll('button').forEach(btn => {
                    const t = (btn.innerText || '').toLowerCase().trim();
                    if (/^(accept|allow all|got it|agree|ok|dismiss|close)$/.test(t)) {
                        btn.click();
                    }
                });
            })()
        """)
    except Exception:
        pass


def run_beat(
    beat_name: str,
    url: str,
    out_dir: str,
    steps: list[dict],
    screen_id: str = SCREEN_ID,
) -> dict:
    """Run a single beat: launch Chrome, start Cap, drive steps, stop Cap.

    Args:
        beat_name: Name of the beat (used for output filenames).
        url: Target URL to navigate to.
        out_dir: Output directory for .cap and results.
        steps: List of step dicts: {action, selector?, url?, ms?, label?}.
        screen_id: Cap screen ID.

    Returns:
        {recordingId, capProjectPath, events, durationMs}
    """
    from playwright.sync_api import sync_playwright

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap_path = str(out / f"{beat_name}.cap")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--remote-debugging-port=9222",
                "--remote-debugging-address=0.0.0.0",
            ],
        )
        context = browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        )
        page = context.new_page()

        # Start Cap
        recording_id = _cap_start(screen_id, cap_path)
        if not recording_id:
            browser.close()
            raise RuntimeError("Failed to start Cap recording")

        start_time = time.time()
        events = []

        try:
            # Navigate
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            _dismiss_overlays(page)
            events.append({"label": "page-load", "elapsed_s": round(time.time() - start_time, 3)})

            # Execute steps
            for step in steps:
                action = step.get("action", "")
                if action == "mark":
                    events.append({
                        "label": step.get("label", "mark"),
                        "elapsed_s": round(time.time() - start_time, 3),
                    })
                elif action == "goto":
                    page.goto(step.get("url", url), wait_until="domcontentloaded")
                    _dismiss_overlays(page)
                elif action == "click":
                    sel = step.get("selector", "")
                    if sel:
                        page.locator(sel).first.click(timeout=10000)
                elif action == "fill":
                    page.locator(step["selector"]).fill(step.get("value", ""))
                elif action == "wait":
                    ms = step.get("ms", 1000)
                    sel = step.get("selector")
                    if sel:
                        page.wait_for_selector(sel, timeout=15000)
                    else:
                        page.wait_for_timeout(ms)
                elif action == "eval":
                    page.evaluate(step.get("js", ""))

            # Hold for closing shot
            page.wait_for_timeout(4000)

        finally:
            _cap_stop(recording_id)
            browser.close()

    duration_ms = int((time.time() - start_time) * 1000)

    # Write results
    result = {
        "recordingId": recording_id,
        "capProjectPath": cap_path,
        "events": events,
        "durationMs": duration_ms,
    }
    result_path = out / f"{beat_name}.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python beat_runner.py <beat-name> <url> <out-dir> [--check]")
        print("       python beat_runner.py --check")
        sys.exit(1)

    if sys.argv[1] == "--check":
        # Verify deps
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            subprocess.run([CAP_BIN, "--version"], capture_output=True, timeout=10, check=True)
            print("✓ Playwright ready, Cap CLI found")
            sys.exit(0)
        except Exception as e:
            print(f"✗ Check failed: {e}")
            sys.exit(1)

    beat_name = sys.argv[1]
    url = sys.argv[2]
    out_dir = sys.argv[3]

    # Load beat steps from stdin or a default
    steps = []
    try:
        data = json.loads(sys.stdin.read())
        steps = data.get("steps", [])
    except Exception:
        # Default: just navigate and wait
        steps = [
            {"action": "wait", "ms": 2000},
            {"action": "mark", "label": "loaded"},
        ]

    result = run_beat(beat_name, url, out_dir, steps)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
