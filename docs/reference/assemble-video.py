# SOURCE: an internal reference project/assemble-video.py
# ROLE: Reference implementation — ffmpeg assembly pipeline.
# Takes a manifest JSON (segments with video/audio/caption), assembles
# a final MP4 via ffmpeg scale/pad/drawtext + concat.
#
# PROJECT-SPECIFIC: nothing — this script is fully generic.
#   The manifest format (output_resolution, segments[].type/video/audio/caption)
#   is the only interface. Reuse as-is or port to Node.js.
#
# DEPENDENCIES: ffmpeg on $PATH (WSL), ffprobe.
#
#!/usr/bin/env python3
"""Assemble the final demo video from short beat clips + VO.

No Premiere/Cap Studio edit session required. Each beat is exported from Cap
and then combined here with:
  - voice-over audio per beat
  - burned-in captions in the bottom safe zone
  - optional camera open/close clips
  - all inputs scaled/padded to a consistent output resolution

Usage:
    uv run python scripts/assemble-video.py recordings/manifest.json

Output:
    recordings/output/demo-output.mp4

Manifest format (recordings/manifest.example.json is a starter):
    {
      "output_resolution": [1707, 1067],
      "output_fps": 60,
      "font_file": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
      "segments": [
        {"type": "camera", "video": "camera/open.mp4"},
        {"type": "screen", "video": "beats/load.mp4", "audio": "vo/load.wav",
         "caption": "I give it the part, the material, and the room..."},
        ...
        {"type": "camera", "video": "camera/close.mp4"}
      ]
    }
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Optional


def run(cmd: List[str], **kwargs) -> None:
    print("$ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def has_audio(path: str) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of",
             "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True,
        )
        return bool(out.stdout.strip())
    except subprocess.CalledProcessError:
        return False



def wrap_caption(text: str, width: int = 60) -> str:
    lines = textwrap.wrap(text, width=width) or [text]
    return "\\n".join(lines)


def build_segment(
    video_path: str,
    audio_path: Optional[str],
    caption: Optional[str],
    output_path: str,
    width: int,
    height: int,
    fps: int,
    font_file: str,
    tmp_dir: Optional[str] = None,
) -> None:
    target = duration(audio_path) if audio_path else duration(video_path)
    video_dur = duration(video_path)

    # Video filter chain
    vfilters: List[str] = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
    ]
    if target > video_dur + 0.05:
        pad_dur = target - video_dur
        vfilters.append(f"tpad=stop_mode=clone:stop_duration={pad_dur:.3f}")
    elif target < video_dur - 0.05:
        vfilters.append(f"trim=0:{target:.3f},setpts=PTS-STARTPTS")
    vfilters.append(f"fps={fps}")

    if caption:
        caption_file: str
        if tmp_dir:
            caption_file = os.path.join(tmp_dir, f"caption_{os.path.basename(output_path)}.txt")
        else:
            import tempfile
            caption_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False).name
        with open(caption_file, 'w', encoding='utf-8') as f:
            f.write(wrap_caption(caption))
        vfilters.append(
            f"drawtext=fontfile={font_file}:"
            f"textfile={caption_file}:"
            f"fontcolor=white:fontsize=28:box=1:boxcolor=black@0.65:boxborderw=10:"
            f"x=(w-text_w)/2:y=h-text_h-40"
        )

    # Audio filter chain
    inputs = ["-i", video_path]
    if audio_path:
        inputs += ["-i", audio_path]
        audio_filter = (
            f"[1:a]aloop=loop=-1:size=10000000,"
            f"atrim=0:{target:.3f},asetpts=PTS-STARTPTS[aout]"
        )
    elif has_audio(video_path):
        audio_filter = (
            f"[0:a]aloop=loop=-1:size=10000000,"
            f"atrim=0:{target:.3f},asetpts=PTS-STARTPTS[aout]"
        )
    else:
        audio_filter = (
            f"anullsrc=channel_layout=stereo:sample_rate=48000:"
            f"duration={target:.3f}[aout]"
        )

    filter_complex = ";".join([f"[0:v]{','.join(vfilters)}[vout]", audio_filter])

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(fps), "-t", f"{target:.3f}",
        output_path,
    ]
    run(cmd)


def assemble(segments: List[dict], output_path: str, width: int, height: int, fps: int) -> None:
    # H.264/HEVC encoders generally require even dimensions.
    if width % 2 or height % 2:
        print(f"Warning: output resolution {width}x{height} has odd dimensions; rounding up to even.")
        width = width + (width % 2)
        height = height + (height % 2)
        print(f"Using {width}x{height} for encoding.")
    with TemporaryDirectory(prefix="assemble_") as tmp:
        seg_files: List[str] = []
        for idx, seg in enumerate(segments, 1):
            seg_out = os.path.join(tmp, f"seg_{idx:03d}.mp4")
            build_segment(
                video_path=seg["video"],
                audio_path=seg.get("audio"),
                caption=seg.get("caption"),
                output_path=seg_out,
                width=width,
                height=height,
                fps=fps,
                font_file=seg.get("font_file", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                tmp_dir=tmp,
            )
            seg_files.append(seg_out)

        list_file = os.path.join(tmp, "concat.txt")
        with open(list_file, "w") as f:
            for path in seg_files:
                f.write(f"file '{path}'\n")

        run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ])


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <manifest.json>", file=sys.stderr)
        sys.exit(1)

    manifest_path = Path(sys.argv[1])
    with open(manifest_path) as f:
        manifest = json.load(f)

    base_dir = manifest_path.parent
    os.chdir(base_dir)

    width, height = manifest.get("output_resolution", [1708, 1068])
    fps = manifest.get("output_fps", 60)
    font_file = manifest.get(
        "font_file", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    )

    segments: List[dict] = []
    for seg in manifest.get("segments", []):
        resolved = {
            "video": str(Path(seg["video"]).resolve()),
            "audio": str(Path(seg["audio"]).resolve()) if seg.get("audio") else None,
            "caption": seg.get("caption"),
            "font_file": font_file,
        }
        segments.append(resolved)

    output = manifest.get("output", "output/demo-output.mp4")
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    assemble(segments, str(output_path), width, height, fps)
    print(f"\n✓ Final video: {output_path}")


if __name__ == "__main__":
    main()
