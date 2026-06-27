"""Preflight gate checks before recording.

Verifies cap-cli, screen targets, Playwright, URL reachability, output dir,
and Windows beat-runner readiness.
"""

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

from capt.export import cap_bin


def _cap_json(*args: str) -> Optional[dict]:
    """Run cap --json and return parsed output."""
    proc = subprocess.run(
        [cap_bin()] + list(args) + ["--json"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    if not out:
        return None
    # Try single-line JSON first
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    # Depth-tracking fallback
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
                except json.JSONDecodeError:
                    return None
    return None


def _powershell_ok() -> bool:
    """Check that PowerShell is reachable from WSL."""
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "echo ok"],
            capture_output=True, text=True, timeout=10,
        )
        return "ok" in proc.stdout.lower()
    except Exception:
        return False


def _url_reachable(url: str) -> bool:
    """Check if a URL responds (401/403 count as reachable)."""
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "Mozilla/5.0"})
        urllib.request.urlopen(req, timeout=15)
        return True
    except urllib.error.HTTPError as e:
        return e.code in (401, 403, 503)
    except Exception:
        return False


def preflight(
    url: Optional[str] = None,
    output_dir: str = "recordings",
    require_playwright: bool = True,
    require_beat_runner: bool = True,
) -> bool:
    """Run all preflight gates. Returns True if all pass."""
    print("=== RECORDING PREFLIGHT ===\n")
    gates = []

    # G1: cap-cli found
    if shutil.which("cap") or Path(cap_bin()).exists():
        print(f"  ✓ G1 cap-cli found  ({cap_bin()})")
        gates.append(True)
    else:
        print("  ✗ G1 cap-cli NOT ready")
        gates.append(False)

    # G2: screen targets
    targets = _cap_json("targets")
    screens = targets.get("screens", []) if targets else []
    if screens:
        print(f"  ✓ G2 screen target  ({screens[0].get('name')} @ {screens[0].get('fps')}fps)")
        gates.append(True)
    else:
        print("  ✗ G2 no screen targets found")
        gates.append(False)

    # G3: Playwright available
    have_pw = False
    try:
        import playwright  # noqa: F401
        have_pw = True
    except ImportError:
        pass
    if have_pw:
        print("  ✓ G3 playwright available")
        gates.append(True)
    elif not require_playwright:
        print("  ⚠ G3 playwright missing (--skip-playwright)")
        gates.append(True)
    else:
        print("  ✗ G3 playwright missing")
        gates.append(False)

    # G4: URL reachable
    if url:
        if _url_reachable(url):
            print(f"  ✓ G4 URL reachable  ({url})")
            gates.append(True)
        else:
            print(f"  ✗ G4 URL unreachable  ({url})")
            gates.append(False)
    else:
        print("  - G4 skipped (no URL)")
        gates.append(True)

    # G5: output dir
    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ G5 output dir  ({output_dir})")
        gates.append(True)
    except Exception:
        print(f"  ✗ G5 output dir not writable  ({output_dir})")
        gates.append(False)

    # G6: PowerShell reachable
    if _powershell_ok():
        print("  ✓ G6 PowerShell reachable")
        gates.append(True)
    else:
        print("  ✗ G6 PowerShell NOT reachable")
        gates.append(False)

    passed = all(gates)
    print(f"\n  Preflight: {'✓ ALL GATES PASS' if passed else '✗ SOME GATES FAILED'}")
    return passed


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Preflight checks before recording")
    ap.add_argument("--url", default=None, help="Target URL to check")
    ap.add_argument("--output-dir", default="recordings")
    ap.add_argument("--skip-playwright", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ok = preflight(args.url, args.output_dir,
                   require_playwright=not args.skip_playwright)
    if args.json:
        print(json.dumps({"ok": ok}))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
