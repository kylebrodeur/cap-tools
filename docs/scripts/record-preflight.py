# SOURCE: an internal reference project/the source project/scripts/record_preflight.py
# ROLE: Reference implementation — preflight gate checks before recording.
# Verifies cap-cli, screen targets, Playwright, URL reachability, output dir.
#
# PROJECT-SPECIFIC: SPACE_URL, EXPORT_DIR_WSL, CAP_CLI_FALLBACK path.
# GENERIC: gate structure (G1-G5), cap JSON parsing, URL check pattern.
#
"""Recording preflight checks (cap-cli + Space + playwright + output dir).

Run from `the source project/`:

    uv run python -m scripts.record_preflight

or

    make record-check
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SPACE_URL = "https://node.your-target-app.example.com"
CAP_CLI_FALLBACK = "/mnt/c/Users/<your-windows-username>/AppData/Local/Cap/cap-cli.exe"
EXPORT_DIR_WSL = "/mnt/d/workspace/recordings"
SCREEN_ID = "65800"
CAP_FPS = "60"


def _cap_bin() -> str:
    """Return the shell command used to invoke cap."""
    if shutil.which("cap"):
        return "cap"
    if Path(CAP_CLI_FALLBACK).exists():
        return CAP_CLI_FALLBACK
    return "cap"


def _cap(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([_cap_bin()] + list(args), capture_output=True, text=True, timeout=120)


def _cap_json(*args: str) -> dict | list | None:
    """Run cap --json and return parsed JSON."""
    r = _cap(*args)
    if r.returncode != 0:
        print(f"  ✗ cap {' '.join(args)} failed: {r.stderr.strip()}")
        return None
    out = r.stdout.strip()
    if not out:
        return None
    lines = out.splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    depth = 0
    buf = []
    started = False
    for line in lines:
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
                except json.JSONDecodeError:
                    return None
    return None


def _get_screen_id() -> str:
    targets = _cap_json("targets", "--json")
    screens = targets.get("screens", []) if isinstance(targets, dict) else []
    for s in screens:
        if s.get("primary"):
            return s["id"]
    if screens:
        return screens[0]["id"]
    return SCREEN_ID


def preflight(url: str = SPACE_URL, require_playwright: bool = True) -> bool:
    """Check everything is ready before recording."""
    print("=== RECORDING PREFLIGHT ===\n")
    gates = []

    if shutil.which("cap") or Path(CAP_CLI_FALLBACK).exists():
        print(f"  ✓ G1 cap-cli found  ({_cap_bin()})")
        gates.append(True)
    else:
        print("  ✗ G1 cap-cli NOT ready — source ~/projects/cap-cli-skill/setup.sh")
        gates.append(False)

    targets = _cap_json("targets", "--json")
    screens = targets.get("screens", []) if isinstance(targets, dict) else []
    if screens:
        print(f"  ✓ G2 screen target  ({screens[0].get('name')} @ {screens[0].get('fps')}fps)")
        gates.append(True)
    else:
        print("  ✗ G2 no screen targets found")
        gates.append(False)

    have_python_pw = False
    try:
        import playwright  # noqa: F401
        have_python_pw = True
    except ImportError:
        pass
    have_cli_pw = shutil.which("playwright") is not None
    if have_python_pw or have_cli_pw:
        print(f"  ✓ G3 playwright available  (python={have_python_pw}, cli={have_cli_pw})")
        gates.append(True)
    else:
        if require_playwright:
            print("  ✗ G3 playwright missing — uv pip install playwright && uv run playwright install chromium")
            gates.append(False)
        else:
            print("  ⚠ G3 playwright missing, but --skip-playwright set — continuing")
            gates.append(True)

    try:
        import urllib.request
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0"})
        try:
            urllib.request.urlopen(req, timeout=15)
            print(f"  ✓ G4 URL reachable  ({url})")
        except urllib.error.HTTPError as e:
            if e.code in (403, 401, 503):
                print(f"  ✓ G4 URL reachable (HTTP {e.code} is an HF block, not a real failure)  ({url})")
            else:
                raise
        gates.append(True)
    except Exception as e:
        print(f"  ✗ G4 URL unreachable  ({e})")
        gates.append(False)

    Path(EXPORT_DIR_WSL).mkdir(parents=True, exist_ok=True)
    print(f"  ✓ G5 output dir  ({EXPORT_DIR_WSL})")
    gates.append(True)

    passed = all(gates)
    print(f"\n  Preflight: {'✓ ALL GATES PASS' if passed else '✗ SOME GATES FAILED'}")
    return passed


def main() -> int:
    ap = argparse.ArgumentParser(description="Recording preflight checks")
    ap.add_argument("--url", default=SPACE_URL, help="Space URL")
    ap.add_argument("--skip-playwright", action="store_true", help="pass even if Python playwright is missing")
    args = ap.parse_args()
    return 0 if preflight(args.url, require_playwright=not args.skip_playwright) else 1


if __name__ == "__main__":
    sys.exit(main())
