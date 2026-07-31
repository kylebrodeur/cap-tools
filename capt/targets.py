"""Discover Cap capture targets (screens/windows/cameras/mics) via
`cap targets --json`, for commands that want a sensible default instead of
asking the user to look up and paste an ID."""

import json
import subprocess
from typing import Optional

from capt.export import cap_bin


def list_targets() -> Optional[dict]:
    """Return `cap targets --json`'s parsed output, or None if the call
    fails for any reason (cap missing, non-zero exit, unparseable output)."""
    try:
        proc = subprocess.run(
            [cap_bin(), "targets", "--json"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def default_screen_id(targets: dict) -> Optional[str]:
    """The primary screen's id if one is marked, else the first screen's."""
    screens = targets.get("screens", [])
    if not screens:
        return None
    for s in screens:
        if s.get("primary"):
            return s.get("id")
    return screens[0].get("id")


def default_mic_name(targets: dict) -> Optional[str]:
    """The first available microphone's name, if any."""
    mics = targets.get("mics", [])
    return mics[0].get("name") if mics else None
