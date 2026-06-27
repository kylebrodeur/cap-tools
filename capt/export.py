"""cap export wrapper — export a .cap project to MP4."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


def cap_bin() -> str:
    """Find the cap CLI binary."""
    import shutil
    if shutil.which("cap"):
        return "cap"
    fallback = "/mnt/c/Users/<your-windows-username>/AppData/Local/Cap/cap-cli.exe"
    if Path(fallback).exists():
        return fallback
    return "cap"


def export(
    project_path: str,
    output_path: str,
    fps: int = 60,
    quality: str = "maximum",
    resolution: Optional[str] = None,
    json_out: bool = False,
) -> dict:
    """Export a .cap project to MP4.

    Returns {"path": str, "status": "completed"} on success.
    """
    cmd = [cap_bin(), "export", project_path, output_path,
           "--fps", str(fps), "--quality", quality]
    if resolution:
        cmd += ["--resolution", resolution]
    if json_out:
        cmd += ["--json"]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        err = proc.stderr.strip() or "export failed"
        if json_out:
            print(json.dumps({"type": "Error", "error": err}))
        sys.exit(f"cap export failed: {err}")

    if json_out:
        # NDJSON output — find the Completed event
        for line in proc.stdout.strip().splitlines():
            try:
                evt = json.loads(line)
                if evt.get("type") == "Completed":
                    return evt
            except json.JSONDecodeError:
                pass

    return {"path": str(Path(output_path).resolve()), "status": "completed"}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Export a .cap project to MP4")
    ap.add_argument("project", help="Path to .cap project")
    ap.add_argument("output", help="Output MP4 path")
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--quality", default="maximum",
                    choices=["maximum", "social", "web", "potato"])
    ap.add_argument("--resolution", default=None, help="WIDTHxHEIGHT")
    ap.add_argument("--json", dest="json_out", action="store_true")
    args = ap.parse_args()

    result = export(args.project, args.output, args.fps, args.quality,
                    args.resolution, args.json_out)
    if args.json_out:
        print(json.dumps(result))
    else:
        print(f"Exported: {result['path']}")


if __name__ == "__main__":
    main()
