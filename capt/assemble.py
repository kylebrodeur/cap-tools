"""ffmpeg assembly pipeline — stitch beat clips + VO + captions into final video.

Port of docs/reference/assemble-video.py. Takes a manifest JSON and produces
a final MP4 via ffmpeg scale/pad/drawtext + concat.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional


def _run(cmd: list[str]) -> None:
    print("$ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def _check_ffmpeg_available() -> None:
    """Fail fast with an actionable message if ffmpeg/ffprobe are missing
    or broken (e.g. a dyld load error from a mismatched Homebrew library),
    rather than a raw CalledProcessError/FileNotFoundError deep in the
    first segment build."""
    for exe in ("ffmpeg", "ffprobe"):
        try:
            r = subprocess.run([exe, "-version"], capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(
                f"capt assemble requires '{exe}' on PATH, but it isn't installed. "
                f"Install ffmpeg (e.g. `brew install ffmpeg`)."
            )
        if r.returncode != 0:
            detail = (r.stderr or r.stdout).strip().splitlines()[:1]
            raise RuntimeError(
                f"capt assemble found '{exe}' on PATH but it failed to run "
                f"({detail[0] if detail else 'no output'}). This is usually a "
                f"broken system install — try reinstalling it (e.g. "
                f"`brew reinstall ffmpeg`)."
            )


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _has_audio(path: str) -> bool:
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


def _wrap_caption(text: str, width: int = 60) -> str:
    lines = textwrap.wrap(text, width=width) or [text]
    return "\\n".join(lines)


def _build_segment(
    video_path: str,
    audio_path: Optional[str],
    caption: Optional[str],
    output_path: str,
    width: int,
    height: int,
    fps: int,
    font_file: str,
    tmp_dir: str,
) -> None:
    target = _duration(audio_path) if audio_path else _duration(video_path)
    video_dur = _duration(video_path)

    vfilters = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
    ]
    if target > video_dur + 0.05:
        vfilters.append(f"tpad=stop_mode=clone:stop_duration={target - video_dur:.3f}")
    elif target < video_dur - 0.05:
        vfilters.append(f"trim=0:{target:.3f},setpts=PTS-STARTPTS")
    vfilters.append(f"fps={fps}")

    if caption:
        caption_file = os.path.join(tmp_dir, f"caption_{os.path.basename(output_path)}.txt")
        with open(caption_file, "w", encoding="utf-8") as f:
            f.write(_wrap_caption(caption))
        vfilters.append(
            f"drawtext=fontfile={font_file}:"
            f"textfile={caption_file}:"
            f"fontcolor=white:fontsize=28:box=1:boxcolor=black@0.65:boxborderw=10:"
            f"x=(w-text_w)/2:y=h-text_h-40"
        )

    inputs = ["-i", video_path]
    if audio_path:
        inputs += ["-i", audio_path]
        audio_filter = (
            f"[1:a]aloop=loop=-1:size=10000000,"
            f"atrim=0:{target:.3f},asetpts=PTS-STARTPTS[aout]"
        )
    elif _has_audio(video_path):
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
    _run(cmd)


def assemble(
    segments: list[dict],
    output_path: str,
    width: int = 1920,
    height: int = 1080,
    fps: int = 60,
    font_file: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
) -> str:
    """Assemble segments into a final video.

    Args:
        segments: List of {video, audio?, caption?} dicts.
        output_path: Output MP4 path.
        width, height: Output resolution.
        fps: Output frame rate.
        font_file: Path to TTF font for captions.

    Returns:
        Path to the assembled video.
    """
    _check_ffmpeg_available()

    if width % 2 or height % 2:
        print(f"Warning: odd dimensions {width}x{height}; rounding up.")
        width += width % 2
        height += height % 2

    with TemporaryDirectory(prefix="assemble_") as tmp:
        seg_files = []
        for idx, seg in enumerate(segments, 1):
            seg_out = os.path.join(tmp, f"seg_{idx:03d}.mp4")
            _build_segment(
                video_path=seg["video"],
                audio_path=seg.get("audio"),
                caption=seg.get("caption"),
                output_path=seg_out,
                width=width, height=height, fps=fps,
                font_file=font_file,
                tmp_dir=tmp,
            )
            seg_files.append(seg_out)

        list_file = os.path.join(tmp, "concat.txt")
        with open(list_file, "w") as f:
            for path in seg_files:
                f.write(f"file '{path}'\n")

        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ])

    return str(Path(output_path).resolve())


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Assemble beat clips into a final video")
    ap.add_argument("manifest", help="Path to manifest JSON")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    with open(manifest_path) as f:
        manifest = json.load(f)

    base_dir = manifest_path.parent
    os.chdir(base_dir)

    width, height = manifest.get("output_resolution", [1920, 1080])
    fps = manifest.get("output_fps", 60)
    font_file = manifest.get("font_file",
                             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

    segments = []
    for seg in manifest.get("segments", []):
        segments.append({
            "video": str(Path(seg["video"]).resolve()),
            "audio": str(Path(seg["audio"]).resolve()) if seg.get("audio") else None,
            "caption": seg.get("caption"),
        })

    output = manifest.get("output", "output/final.mp4")
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = assemble(segments, str(output_path), width, height, fps, font_file)
    if args.json:
        print(json.dumps({"path": result, "status": "completed"}))
    else:
        print(f"\n✓ Final video: {result}")


if __name__ == "__main__":
    main()
