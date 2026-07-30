"""Zoom segment builder from event timestamps.

Generates timeline.zoomSegments for Cap's project-config.json from event
timestamps collected during a recording run. Each event becomes a zoom
segment that Cap will auto-follow during export.
"""

import json
from typing import Optional


def build_zoom_segments(
    events: list[dict],
    amount: float = 2.0,
    pre_seconds: float = 0.5,
    hold_seconds: float = 2.5,
    min_gap_seconds: float = 1.0,
    mode: str = "auto",
    instant_animation: bool = False,
) -> list[dict]:
    """Build zoom segments from event timestamps.

    Args:
        events: List of {label, elapsed_s} dicts from the recording run.
        amount: Zoom level (1.5 = subtle, 2.0 = strong demo zoom).
        pre_seconds: Start zoom this many seconds before the event.
        hold_seconds: Stay zoomed this many seconds after the event.
        min_gap_seconds: Merge segments closer than this gap.
        mode: "auto" (Cap follows cursor) or "manual".
        instant_animation: True for cut, False for animated zoom.

    Returns:
        List of zoom segment dicts ready for project-config.json.
    """
    if not events:
        return []

    # Build raw segments from events
    raw = []
    for evt in events:
        t = evt.get("elapsed_s", 0)
        raw.append({
            "start": max(0, t - pre_seconds),
            "end": t + hold_seconds,
            "amount": amount,
            "mode": mode,
            "glideDirection": "none",
            "glideSpeed": 0.5,
            "instantAnimation": instant_animation,
            "edgeSnapRatio": 0.25,
        })

    # Sort by start time
    raw.sort(key=lambda s: s["start"])

    # Merge overlapping/nearby segments
    merged = []
    for seg in raw:
        if not merged:
            merged.append(seg)
            continue
        prev = merged[-1]
        gap = seg["start"] - prev["end"]
        if gap < min_gap_seconds:
            # Merge: extend the previous segment
            prev["end"] = max(prev["end"], seg["end"])
        else:
            merged.append(seg)

    return merged


def merge_zoom_segments(config: dict, zoom_segments: list[dict]) -> dict:
    """Merge generated zoom segments into an existing project-config.json.

    `cap project config set` replaces the whole document (omitted fields reset
    to defaults), so any write must start from the current config and only
    replace `timeline.zoomSegments` — never a partial object. This mirrors the
    "read, merge, show before writing" pattern documented in Cap's own
    Agent Workflows guide.

    Args:
        config: The project's current config, as returned by `read_config`.
        zoom_segments: Output of `build_zoom_segments`.

    Returns:
        A new config dict with `timeline.zoomSegments` replaced. Does not
        mutate `config`.
    """
    merged = json.loads(json.dumps(config))  # deep copy without extra deps
    merged.setdefault("timeline", {})["zoomSegments"] = zoom_segments
    return merged


def create_tracker():
    """Create an event tracker for use during recording.

    Returns a tracker object with .mark(label) and .events() methods.
    """
    import time

    class Tracker:
        def __init__(self):
            self._start = time.time()
            self._events: list[dict] = []

        def mark(self, label: str) -> None:
            """Record an event at the current time."""
            self._events.append({
                "label": label,
                "elapsed_s": round(time.time() - self._start, 3),
            })

        def events(self) -> list[dict]:
            """Return all recorded events."""
            return list(self._events)

    return Tracker()
