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
