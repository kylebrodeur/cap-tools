"""3D camera-scene segment builder from event timestamps.

Generates timeline.camera3dSegments for Cap 0.6+ project-config.json from
the events sidecar ({label, elapsed_s} list) — or from fixed poses that
ignore events entirely. A 3D scene moves the *camera* around the recording
(orbit/tilt/zoom/fov) instead of cropping toward the cursor like
timeline.zoomSegments; the two compose (scenes + zoom in one config).

Geometry contract (Cap's own doc-strings, verified by write→read round-trip
and a live headless export on 0.6.0):
  - content plane's longest side spans 2 world units, centered at origin,
    facing +Z;
  - tiltX/tiltY/roll orbit the camera (Euler YXZ, roll innermost);
    rotateX/rotateY rotate the content plane;
  - zoom = camera distance (larger = smaller on screen);
  - fov = vertical FOV; apparent size ∝ 1/(zoom·tan(fov/2));
  - panX/panY truck the camera (+x right, +y up);
  - keyframe time is seconds relative to segment start; only
    tiltX/tiltY/rotateX/rotateY/fov/blurStrength/blurFalloff/
    blurFocusSize/blurFocusX/blurFocusY/blurAngle/blurDirPosition are
    animatable (not roll/panX/panY/zoom);
  - keyframes: {time, value, outEasing, inEasing} bezier split-handles;
    absent handles → cubic ease-in-out (P1[0.65,0], P2[0.35,1]).
"""

import json

STYLES = ("reveal", "punch", "orbit", "flat")

# Pre/hold/gap mirror capt.zoom.build_zoom_segments defaults so `punch`
# windows land where zoom windows would.
PUNCH_PRE_SECONDS = 0.8
PUNCH_HOLD_SECONDS = 2.5
PUNCH_MIN_GAP_SECONDS = 1.0

POSE_REVEAL = {"tiltX": 8.0, "tiltY": -12.0, "zoom": 1.08, "fov": 50.0}
POSE_PUNCH = {"tiltX": 10.0, "tiltY": -15.0, "zoom": 1.12}
POSE_ORBIT_TILT_X = 6.0
POSE_ORBIT_TILT_Y_FROM = -20.0
POSE_ORBIT_TILT_Y_TO = 20.0


def _default_properties() -> dict:
    """Full properties object the exporter expects; plan poses override."""
    return {
        "tiltX": 0.0, "tiltY": 0.0, "roll": 0.0, "rotateX": 0.0, "rotateY": 0.0,
        "zoom": 1.0, "fov": 50.0, "panX": 0.0, "panY": 0.0,
    }


def _segment(start: float, end: float, properties: dict,
             tracks: dict | None = None, transition_in: float = 0.5,
             transition_out: float = 0.5, blur: float = 0.0) -> dict:
    props = _default_properties()
    props.update(properties)
    seg = {
        "start": round(start, 3),
        "end": round(end, 3),
        "enabled": True,
        "properties": props,
        "tracks": tracks or {},
        "transitionIn": transition_in,
        "transitionOut": transition_out,
        "blur": {"mode": "none", "strength": blur, "falloff": 0.45, "focusX": 0.5,
                 "focusY": 0.5, "focusSize": 0.4, "angle": 0.0, "dirPosition": 0.5,
                 "bokeh": False},
    }
    return seg


def build_scene_segments(
    events: list[dict],
    style: str = "reveal",
    duration: float | None = None,
    transition_in: float = 0.5,
    transition_out: float = 0.5,
    blur: float = 0.0,
) -> list[dict]:
    """Build camera3dSegments from the events sidecar.

    Args:
        events: List of {label, elapsed_s} dicts from the recording run
            (ignored by the "reveal"/"orbit"/"flat" styles).
        style: One of STYLES — "reveal" (default; one full-clip segment,
            screen leans back in space), "punch" (one segment per event,
            camera pushes in around each click), "orbit" (one segment,
            tiltY sweeps -20° → +20° across the clip), or "flat" (no-op).
        duration: Clip length in seconds. Required for reveal/orbit when
            it cannot be inferred from events; punch derives segment
            bounds from event times.
        transition_in/transition_out: Ease-in/out ramp (seconds) on each
            segment.
        blur: Background blur strength (px radius at 1080p; 0 = none).

    Returns:
        List of camera3dSegments dicts ready for project-config.json.
    """
    if style not in STYLES:
        raise ValueError(f"unknown scene style {style!r}; valid styles: {', '.join(STYLES)}")

    if style == "flat":
        return []

    if duration is not None and duration <= 0:
        raise ValueError("duration must be positive")

    if style == "reveal":
        if duration is None:
            duration = _events_duration(events)
        return [_segment(0.0, duration, POSE_REVEAL,
                         transition_in=transition_in,
                         transition_out=transition_out, blur=blur)]

    if style == "orbit":
        if duration is None:
            duration = _events_duration(events)
        tracks = {"tiltY": [
            {"time": 0.0, "value": POSE_ORBIT_TILT_Y_FROM},
            {"time": round(duration, 3), "value": POSE_ORBIT_TILT_Y_TO},
        ]}
        return [_segment(0.0, duration, {"tiltX": POSE_ORBIT_TILT_X},
                         tracks=tracks, transition_in=transition_in,
                         transition_out=transition_out, blur=blur)]

    # punch: one segment per event, windows like zoom (pre/hold), merged
    # when the gap between consecutive windows is under 1s.
    raw = []
    for evt in events:
        t = evt.get("elapsed_s", 0)
        raw.append(_segment(max(0, t - PUNCH_PRE_SECONDS), t + PUNCH_HOLD_SECONDS,
                            POSE_PUNCH, transition_in=transition_in,
                            transition_out=transition_out, blur=blur))
    raw.sort(key=lambda s: s["start"])
    merged = []
    for seg in raw:
        if not merged:
            merged.append(seg)
            continue
        prev = merged[-1]
        if seg["start"] - prev["end"] < PUNCH_MIN_GAP_SECONDS:
            prev["end"] = max(prev["end"], seg["end"])
        else:
            merged.append(seg)
    return merged


def _events_duration(events: list[dict]) -> float:
    """Last event's elapsed_s + hold, or raise if there are none — callers
    without a real duration should pass --duration explicitly."""
    times = [evt.get("elapsed_s", 0) for evt in events]
    if not times:
        raise ValueError(
            "duration required (no events to infer it from); pass --duration or set duration="
        )
    return max(times) + 2.5


def merge_scene_segments(config: dict, scene_segments: list[dict]) -> dict:
    """Merge generated camera3dSegments into an existing project-config.json.

    Like merge_zoom_segments, replaces the whole document's timeline.
    camera3dSegments key wholesale — scenes replace each other (compose
    with zoom, not with other scenes), so applying a new scene overwrites
    any previous one. Returns a new dict; does not mutate `config`.
    """
    merged = json.loads(json.dumps(config))  # deep copy without extra deps
    merged.setdefault("timeline", {})["camera3dSegments"] = scene_segments
    return merged