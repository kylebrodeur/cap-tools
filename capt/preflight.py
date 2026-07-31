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

from capt import tailscale
from capt.export import cap_bin


def _cap_json(*args: str) -> Optional[dict]:
    """Run cap --json and return parsed output."""
    try:
        proc = subprocess.run(
            [cap_bin()] + list(args) + ["--json"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
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
    marker_source: str = "steps",
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

    # G4: URL reachable — for HTTPS targets, resolve to the Tailscale
    # MagicDNS name (full address, not just IP) when available.
    if url:
        if url.lower().startswith("https://"):
            resolved = tailscale.resolve_target(url)
            if resolved != url:
                print(f"  → HTTPS target rewritten to Tailscale address: {resolved}")
                url = resolved
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

    # G6: platform-specific gate — PowerShell on Windows/WSL, global-capture
    # permission on macOS (only when that marker source is requested).
    import platform as _platform

    def _is_wsl() -> bool:
        try:
            with open("/proc/version") as f:
                return "microsoft" in f.read().lower()
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
