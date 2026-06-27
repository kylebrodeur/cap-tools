"""Tailscale helpers — discover the full MagicDNS address for HTTPS targets.

When a recording target requires HTTPS (e.g. WordPress with HTTPS constants,
Secure cookies, or HSTS), a bare IP won't work. Tailscale serve exposes the
app over HTTPS at the node's MagicDNS name (e.g. redacted.ts.net).

This module finds that full address via the terminal — `tailscale status
--json` reports `Self.DNSName`, which is the complete name, not just the IP.

Tailscale is OPTIONAL. It is only needed for HTTPS targets. Plain HTTP
targets can use 127.0.0.1 / the WSL IP directly.

The `tailscale` CLI may live on either side of the WSL boundary:
  - WSL native:   `tailscale`
  - Windows host: `tailscale.exe`
We try both so this works regardless of where Tailscale is installed.
"""

import json
import shutil
import subprocess
from typing import Optional


def _tailscale_bin() -> Optional[str]:
    """Locate a usable tailscale binary (WSL native or Windows host)."""
    for candidate in ("tailscale", "tailscale.exe"):
        if shutil.which(candidate):
            return candidate
    return None


def is_available() -> bool:
    """True if a tailscale binary is on PATH (either side of WSL)."""
    return _tailscale_bin() is not None


def _status() -> Optional[dict]:
    """Return parsed `tailscale status --json`, or None if unavailable/down."""
    binary = _tailscale_bin()
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "status", "--json"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def is_running() -> bool:
    """True if Tailscale is up and the node is connected."""
    status = _status()
    if not status:
        return False
    return status.get("BackendState") == "Running"


def magic_dns_name() -> Optional[str]:
    """Return this node's full MagicDNS name without the trailing dot.

    e.g. "redacted.ts.net". Returns None if Tailscale is not
    running or MagicDNS is not enabled.
    """
    status = _status()
    if not status:
        return None
    self_node = status.get("Self") or {}
    dns_name = self_node.get("DNSName") or ""
    dns_name = dns_name.rstrip(".")  # status reports a trailing dot
    return dns_name or None


def https_url(path: str = "/") -> Optional[str]:
    """Build an HTTPS URL at the node's MagicDNS name.

    Returns e.g. "https://redacted.ts.net/" or None if the full
    name can't be resolved. Useful when `tailscale serve` is exposing a
    local app over HTTPS on port 443.
    """
    name = magic_dns_name()
    if not name:
        return None
    if not path.startswith("/"):
        path = "/" + path
    return f"https://{name}{path}"


def serve_status() -> Optional[dict]:
    """Return parsed `tailscale serve status --json`, or None.

    Lets callers confirm an app is actually being served over HTTPS before
    pointing the beat-runner at the MagicDNS name.
    """
    binary = _tailscale_bin()
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "serve", "status", "--json"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def resolve_target(url: str) -> str:
    """Rewrite an HTTPS target to use the MagicDNS name when appropriate.

    If `url` is HTTPS and points at localhost / a bare IP, and Tailscale is
    running with a MagicDNS name, swap the host for the full Tailscale
    address (preserving path/query). Otherwise return `url` unchanged.

    HTTP targets are returned as-is — Tailscale is only needed for HTTPS.
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    if parsed.scheme != "https":
        return url

    host = parsed.hostname or ""
    needs_rewrite = (
        host in ("localhost", "127.0.0.1", "0.0.0.0")
        or host.startswith("172.")
        or host.startswith("192.168.")
        or host.startswith("10.")
    )
    if not needs_rewrite:
        return url

    name = magic_dns_name()
    if not name:
        return url

    netloc = name
    if parsed.port and parsed.port != 443:
        netloc = f"{name}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Tailscale MagicDNS helpers")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    info = {
        "available": is_available(),
        "running": is_running(),
        "magic_dns_name": magic_dns_name(),
        "https_url": https_url(),
    }
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        if not info["available"]:
            print("Tailscale: not installed")
        elif not info["running"]:
            print("Tailscale: installed but not running")
        else:
            print(f"Tailscale: {info['magic_dns_name']}")
            print(f"HTTPS URL: {info['https_url']}")


if __name__ == "__main__":
    main()
