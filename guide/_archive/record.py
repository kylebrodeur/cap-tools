#!/usr/bin/env python3
"""
record.py - Capture screen + microphone + click events simultaneously.

Usage:
    uv run spike/record.py
    uv run spike/record.py --list-sources
    uv run spike/record.py --screen 1 --mic "Microphone (USB Audio Device)"

Press Enter to START, press Enter again to STOP.
Outputs:
    spike-output/recording/recording.mp4
    spike-output/recording/events.json
"""

import argparse
import ctypes
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from ctypes import wintypes

from pynput import mouse

# ── Config ────────────────────────────────────────────────────────────────────
SPIKE_ROOT  = Path(__file__).parent / "spike-output"
OUT_DIR     = SPIKE_ROOT / "recording"
FRAMERATE   = 30
CRF         = 18       # H.264 quality — 18 = very high, 23 = default
CLICK_OFFSET = 0.5     # seconds after click used by extract_frames.py
# ─────────────────────────────────────────────────────────────────────────────

OUT_DIR.mkdir(parents=True, exist_ok=True)

events: list[dict] = []
start_time: float | None = None
recording = False


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * 32),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record selected screen + optional microphone.")
    parser.add_argument("--screen", type=int, default=0, help="Screen index from --list-sources output.")
    parser.add_argument("--mic", type=str, default=None, help="Microphone display name (supports partial match).")
    parser.add_argument("--no-audio", action="store_true", help="Disable microphone capture.")
    parser.add_argument("--list-sources", action="store_true", help="Print available screens and microphones, then exit.")
    return parser.parse_args()


def list_screens() -> list[dict]:
    user32 = ctypes.windll.user32
    monitors: list[dict] = []

    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def _callback(hmonitor, hdc, lprect, lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        ok = user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        if ok:
            width = int(info.rcMonitor.right - info.rcMonitor.left)
            height = int(info.rcMonitor.bottom - info.rcMonitor.top)
            monitors.append(
                {
                    "name": info.szDevice,
                    "x": int(info.rcMonitor.left),
                    "y": int(info.rcMonitor.top),
                    "width": width,
                    "height": height,
                    "primary": bool(info.dwFlags & 1),
                }
            )
        return 1

    user32.EnumDisplayMonitors(0, 0, callback_type(_callback), 0)

    monitors.sort(key=lambda m: (not m["primary"], m["x"], m["y"]))
    return monitors


def list_microphones() -> list[str]:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    lines = output.splitlines()

    devices: list[str] = []
    for line in lines:
        # ffmpeg output varies by version. Some builds print explicit
        # "DirectShow audio devices" sections, others tag each line with
        # "(audio)" / "(video)". Match tagged audio lines first, then
        # keep a fallback for older sectioned output.
        tagged = re.search(r'"([^"]+)"\s*\((audio|video)\)', line)
        if tagged:
            if tagged.group(2) == "audio":
                name = tagged.group(1).strip()
                if name and name not in devices:
                    devices.append(name)
            continue

        if "DirectShow audio devices" in line:
            continue

        if "DirectShow video devices" in line:
            continue

        match = re.search(r'"([^"]+)"', line)
        if match and "alternative name" not in line.lower():
            # Fallback for legacy ffmpeg layout where this line appears in
            # an audio-only section.
            name = match.group(1).strip()
            if "microphone" in name.lower() and name not in devices:
                devices.append(name)

    return devices


def resolve_microphone(requested: str | None, microphones: list[str]) -> str | None:
    if not microphones:
        return None
    if requested is None:
        return microphones[0]

    lower = requested.lower()
    exact = [m for m in microphones if m.lower() == lower]
    if exact:
        return exact[0]

    partial = [m for m in microphones if lower in m.lower()]
    if len(partial) == 1:
        return partial[0]

    if len(partial) > 1:
        print("Microphone name is ambiguous. Matches:")
        for m in partial:
            print(f"  - {m}")
        sys.exit(1)

    print(f"Microphone not found: {requested}")
    print("Run with --list-sources to view valid microphone names.")
    sys.exit(1)


def print_sources(screens: list[dict], microphones: list[str]) -> None:
    print("Available screens:")
    for i, s in enumerate(screens):
        primary_tag = " (primary)" if s["primary"] else ""
        print(f"  [{i}] {s['name']}  {s['width']}x{s['height']} @ ({s['x']},{s['y']}){primary_tag}")

    print("\nAvailable microphones:")
    if microphones:
        for i, m in enumerate(microphones):
            print(f"  [{i}] {m}")
    else:
        print("  (none detected via ffmpeg dshow)")


def build_ffmpeg_command(outfile: Path, screen: dict, microphone: str | None) -> list[str]:
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "gdigrab",
        "-framerate",
        str(FRAMERATE),
        "-offset_x",
        str(screen["x"]),
        "-offset_y",
        str(screen["y"]),
        "-video_size",
        f"{screen['width']}x{screen['height']}",
        "-i",
        "desktop",
    ]

    if microphone:
        command.extend(["-f", "dshow", "-i", f"audio={microphone}"])

    command.extend(
        [
            "-c:v",
            "libx264",
            "-crf",
            str(CRF),
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
        ]
    )

    if microphone:
        command.extend(["-c:a", "aac", "-b:a", "160k", "-shortest"])

    command.append(str(outfile))
    return command


def on_click(x, y, button, pressed):
    if pressed and recording and start_time is not None:
        t = round(time.time() - start_time, 3)
        events.append({"t": t, "x": x, "y": y, "button": button.name})


def main() -> None:
    global recording, start_time

    args = parse_args()
    screens = list_screens()
    microphones = list_microphones()

    if not screens:
        print("No screens detected.")
        sys.exit(1)

    if args.list_sources:
        print_sources(screens, microphones)
        return

    if args.screen < 0 or args.screen >= len(screens):
        print(f"Invalid --screen index: {args.screen}")
        print(f"Use --list-sources to choose a screen from 0 to {len(screens) - 1}.")
        sys.exit(1)

    selected_screen = screens[args.screen]
    selected_mic = None if args.no_audio else resolve_microphone(args.mic, microphones)

    outfile = OUT_DIR / "recording.mp4"
    if outfile.exists():
        outfile.unlink()

    ffmpeg_command = build_ffmpeg_command(outfile, selected_screen, selected_mic)

    print("Recording configuration:")
    print(
        f"  Screen      : [{args.screen}] {selected_screen['name']} "
        f"{selected_screen['width']}x{selected_screen['height']} @ ({selected_screen['x']},{selected_screen['y']})"
    )
    print(f"  Microphone  : {selected_mic or 'disabled'}")
    print(f"  Video output: {outfile}")
    print()

    listener = mouse.Listener(on_click=on_click)
    listener.start()

    input("Press Enter to START recording...")
    start_time = time.time()
    recording = True

    print(f"  Recording -> {outfile}")
    print("  (narrate each action clearly, pause ~1s after each click)")
    print()

    ffmpeg = subprocess.Popen(
        ffmpeg_command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    input("Press Enter to STOP recording...")
    recording = False

    if ffmpeg.stdin:
        ffmpeg.stdin.write("q\n")
        ffmpeg.stdin.flush()

    ffmpeg.wait()
    stderr_output = ffmpeg.stderr.read() if ffmpeg.stderr else ""
    listener.stop()

    if ffmpeg.returncode != 0:
        print("ffmpeg failed. Last output:")
        tail = "\n".join(stderr_output.splitlines()[-20:])
        print(tail or "(no ffmpeg output)")
        sys.exit(ffmpeg.returncode)

    events_file = OUT_DIR / "events.json"
    events_file.write_text(json.dumps(events, indent=2))

    duration = round(time.time() - start_time, 1) if start_time else 0.0
    print(f"\n  {len(events)} clicks captured over {duration}s")
    print(f"  events.json  -> {events_file}")
    print(f"  recording    -> {outfile}")
    print()
    print("Next: run  uv run spike/transcribe.py")


if __name__ == "__main__":
    main()
