"""project-config.json builder with presets.

Builds and writes Cap's project-config.json without opening Cap Desktop Studio.
See docs/PROJECT-CONFIG-SCHEMA.md for the full schema.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from capt.export import cap_bin


# ── Presets ───────────────────────────────────────────────────────────────────

def _demo_wallpaper_path() -> str:
    """Path to one of Cap Desktop's bundled wallpaper assets (Windows only).

    Cap installs its bundled backgrounds under the current Windows user's
    own AppData, so this resolves per-user rather than being hardcoded to
    whoever happened to build this preset.
    """
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "<user>"
    return f"\\\\?\\C:\\Users\\{username}\\AppData\\Local\\Cap\\assets\\backgrounds\\cities\\sf.jpg"


PRESET_DEMO = {
    "background": {
        "source": {"type": "wallpaper", "path": _demo_wallpaper_path()},
        "blur": 0.0, "padding": 10.0, "rounding": 7.5, "roundingType": "squircle",
        "inset": 0, "crop": None, "shadow": 73.6,
        "advancedShadow": {"size": 14.4, "opacity": 68.1, "blur": 3.8},
        "border": None,
    },
    "camera": {"hide": True},
    "audio": {"mute": False},
    "cursor": {
        "hide": False, "size": 100, "type": "auto", "animationStyle": "mellow",
        "motionBlur": 0.5, "raw": False, "useSvg": True,
    },
    "hotkeys": {"show": False},
    "screenMotionBlur": 0.5,
    "screenMovementSpring": {"stiffness": 200.0, "damping": 40.0, "mass": 2.25},
}

PRESET_CLEAN = {
    "background": {
        "source": {"type": "color", "value": [0, 0, 0], "alpha": 255},
        "blur": 0.0, "padding": 0.0, "rounding": 0.0, "shadow": 0.0,
        "roundingType": "squircle", "inset": 0, "crop": None, "border": None,
    },
    "camera": {"hide": True},
    "audio": {"mute": False},
    "cursor": {"hide": False, "size": 100, "animationStyle": "mellow", "motionBlur": 0.0, "type": "auto"},
    "hotkeys": {"show": False},
    "screenMotionBlur": 0.0,
    "screenMovementSpring": {"stiffness": 200.0, "damping": 40.0, "mass": 2.25},
}

PRESET_RAW = {
    "background": {
        "source": {"type": "color", "value": [0, 0, 0], "alpha": 255},
        "blur": 0.0, "padding": 0.0, "rounding": 0.0, "shadow": 0.0,
        "roundingType": "squircle", "inset": 0, "crop": None, "border": None,
    },
    "camera": {"hide": True},
    "audio": {"mute": False},
    "cursor": {"hide": True},
    "hotkeys": {"show": False},
    "screenMotionBlur": 0.0,
    "screenMovementSpring": {"stiffness": 200.0, "damping": 40.0, "mass": 2.25},
}

PRESETS = {"demo": PRESET_DEMO, "clean": PRESET_CLEAN, "raw": PRESET_RAW}


# ── Base config skeleton ──────────────────────────────────────────────────────

def _base_config() -> dict:
    return {
        "aspectRatio": None,
        "timeline": {
            "segments": [{"recordingSegment": 0, "timescale": 1.0, "start": 0.0, "end": 9999}],
            "zoomSegments": [],
            "sceneSegments": [], "maskSegments": [],
            "textSegments": [], "captionSegments": [], "keyboardSegments": [],
        },
        "captions": None,
        "keyboard": None,
        "clips": [{"index": 0, "offsets": {"camera": 0.0, "mic": 0.0, "system_audio": 0.0}}],
        "annotations": [],
    }


# ── Public API ────────────────────────────────────────────────────────────────

def build_config(
    preset: str = "demo",
    zoom_segments: Optional[list] = None,
    background: Optional[dict] = None,
    cursor: Optional[dict] = None,
    spring: str = "snappy",
    captions: bool = False,
    keyboard: bool = False,
    trim_end: Optional[float] = None,
) -> dict:
    """Build a complete project-config.json from options."""
    cfg = _base_config()
    preset_cfg = PRESETS.get(preset, PRESET_DEMO)
    cfg.update({k: v for k, v in preset_cfg.items() if k not in ("background", "cursor")})

    if background:
        cfg["background"] = background
    else:
        cfg["background"] = preset_cfg.get("background", PRESET_DEMO["background"])

    if cursor:
        cfg["cursor"] = cursor
    else:
        cfg["cursor"] = preset_cfg.get("cursor", PRESET_DEMO["cursor"])

    if spring == "smooth":
        cfg["screenMovementSpring"] = {"stiffness": 120.0, "damping": 14.0, "mass": 1.0}

    if zoom_segments:
        cfg["timeline"]["zoomSegments"] = zoom_segments

    if trim_end is not None:
        cfg["timeline"]["segments"][0]["end"] = trim_end

    if not captions:
        cfg["captions"] = None
    if not keyboard:
        cfg["keyboard"] = None

    return cfg


def read_config(project_path: str) -> dict:
    """Read a .cap project's current project-config.json."""
    proc = subprocess.run(
        [cap_bin(), "project", "config", "get", project_path, "--json"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        sys.exit(f"cap project config get failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout.strip())


def write_config(project_path: str, config: dict) -> None:
    """Write a full project-config.json to a .cap project."""
    settings = json.dumps(config)
    proc = subprocess.run(
        [cap_bin(), "project", "config", "set", project_path,
         "--settings-json", settings, "--json"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        sys.exit(f"cap project config set failed: {proc.stderr.strip()}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Read/write Cap project-config.json")
    ap.add_argument("project", help="Path to .cap project")
    ap.add_argument("--get", action="store_true", help="Read current config")
    ap.add_argument("--preset", default=None, choices=list(PRESETS), help="Apply a preset")
    ap.add_argument("--zoom", default=None, help="Path to zoom segments JSON")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.get:
        cfg = read_config(args.project)
        if args.json:
            print(json.dumps(cfg, indent=2))
        else:
            print(json.dumps(cfg, indent=2))
    elif args.preset:
        zoom = None
        if args.zoom:
            zoom = json.loads(Path(args.zoom).read_text())
        cfg = build_config(preset=args.preset, zoom_segments=zoom)
        write_config(args.project, cfg)
        print(f"Applied preset '{args.preset}' to {args.project}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
