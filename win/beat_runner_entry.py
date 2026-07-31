"""Windows-side entry point for `capt record` invoked from WSL over
PowerShell. Thin shim: parses argv, calls the shared, vendored
capt.record.beat.run_beat(), prints the result as one JSON line for WSL to
read from stdout.

This file plus a full copy of the capt/ package are what live at
C:\\cap-tools\\ after running win/install.ps1 — see
docs/superpowers/specs/2026-07-30-macos-record-support-design.md.
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("url", nargs="?", default=None)
    ap.add_argument("out_dir")
    ap.add_argument("--screen", default=None)
    ap.add_argument("--window", default=None)
    ap.add_argument("--steps", default=None)
    ap.add_argument("--marker-source", default="steps")
    ap.add_argument("--export-to", default=None)
    ap.add_argument("--mic", default=None)
    ap.add_argument("--system-audio", action="store_true")
    ap.add_argument("--camera", default=None)
    ap.add_argument("--until-stopped", action="store_true")
    args = ap.parse_args()

    from capt.record.beat import run_beat

    step_list = []
    if args.steps:
        step_list = json.loads(Path(args.steps).read_text())

    result = run_beat(
        args.url, step_list, args.out_dir, name=args.name,
        screen_id=args.screen, window_id=args.window, marker_source=args.marker_source,
        export_to=args.export_to,
        mic=args.mic, system_audio=args.system_audio, camera=args.camera,
        until_stopped=args.until_stopped,
    )
    print(json.dumps(asdict(result)))


if __name__ == "__main__":
    main()
