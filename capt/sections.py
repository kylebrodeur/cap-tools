"""Section extraction from a styled Cap recording.

Pipeline for demo-timeline workflows: record the WHOLE product take once
(completeness verified via .beats.json), apply effects (zoom/3D scenes/
backgrounds) to the full take, `cap export` it once, then cut labeled
sections out of the exported MP4 with ffmpeg. `cap export` ignores
timeline trim headlessly (verified 0.6.0), so section splits happen
post-export — fast, deterministic, and re-cuttable without re-rendering.

Section sources, in order of preference:
  - .beats.json (written by `capt record` with steps): each verified beat
    becomes section boundaries {label}:start -> next beat's start.
  - explicit JSON: [{"name": ..., "start_s": ..., "end_s": ...}, ...]
"""
import json
import re
import shutil
import subprocess
from pathlib import Path


def sections_from_beats(beats: list, default_hold_s: float = 1.0,
                         labeled_only: bool = False) -> list:
    """Convert a beat report (capt record's .beats.json 'beats' list) into
    sections. Each beat spans from its own time to the NEXT KEPT beat's
    time (the last one holds default_hold_s past its end).

    labeled_only=True keeps only beats whose label doesn't look like an
    auto-generated action label ("action:target", "wait-N", "goto:url") —
    i.e. the named script beats. Their end extends to the next labeled
    beat's start, so each section spans its full paced window.

    Returns [{name, start_s, end_s}] sorted by start.
    """
    auto_label = re.compile(
        r"^(goto:|click:|fill:|wait-\d+|mark-\d+)")

    def _kept(label: str) -> bool:
        return not labeled_only or not auto_label.match(label)

    times = []
    for b in beats:
        start = None
        for evt_key in ("start_elapsed_s", "elapsed_s"):
            if evt_key in b:
                start = float(b[evt_key])
                break
        if start is None:
            continue
        label = b.get("label") or f"beat-{b.get('index', len(times))}"
        if _kept(label):
            times.append((max(0.0, start), label))
    times.sort()
    sections = []
    for i, (start, label) in enumerate(times):
        end = times[i + 1][0] if i + 1 < len(times) else start + default_hold_s
        sections.append({"name": label, "start_s": round(start, 3),
                         "end_s": round(max(end, start + 0.1), 3)})
    return sections


def sections_from_events(events: list, default_hold_s: float = 2.5) -> list:
    """Convert an events sidecar ([{label, elapsed_s}]) into sections —
    same shape as sections_from_beats but for takes without beat reports
    (manual marks, global-capture clicks)."""
    beats = [{"index": i, "label": e.get("label", f"event-{i}"),
              "elapsed_s": e.get("elapsed_s", 0.0)}
             for i, e in enumerate(events)]
    return sections_from_beats(beats, default_hold_s=default_hold_s)

def load_sections(source: str, labeled_only: bool = False) -> list:
    """Load sections from a .beats.json (beat report) or a hand-written
    sections JSON ([{name, start_s, end_s}]). labeled_only applies only to
    beats reports: keep the named script beats, drop auto-labeled ones."""
    data = json.loads(Path(source).read_text())
    if isinstance(data, dict) and "beats" in data:
        return sections_from_beats(data["beats"], labeled_only=labeled_only)
    if isinstance(data, list):
        if data and "start_s" in data[0]:
            return data
        if data and "elapsed_s" in data[0]:
            return sections_from_events(data)
    raise ValueError(
        f"{source}: expected a beats report, a sections list "
        "([{name, start_s, end_s}]), or an events sidecar"
    )


def cut_section(video: str, section: dict, out_path: str,
                reencode: bool = True) -> str:
    """Cut one section out of an exported MP4 with ffmpeg.

    reencode=True (default) re-encodes — frame-accurate cuts, safe for
    timeline assembly. reencode=False stream-copies — fast but cuts land
    on keyframes (bounds can drift by up to a GOP).

    Returns the output path.
    """
    out = str(Path(out_path))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.1, section["end_s"] - section["start_s"])
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", f"{section['start_s']:.3f}", "-i", video]
    if reencode:
        cmd += ["-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium",
                "-crf", "18", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-t", f"{dur:.3f}", "-c", "copy"]
    cmd += [out]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg section cut failed for {section['name']}: {proc.stderr.strip()}")
    return out


def export_sections(project_cap: str, styled_mp4: str, out_dir: str,
                    sections: list, prefix: str = "section",
                    reencode: bool = True) -> list:
    """Cut every section out of the styled full-take export.

    project_cap: used only to name outputs after the take.
    Returns the list of written MP4 paths, one per section, in order.
    """
    outputs = []
    take = Path(project_cap).stem
    for i, sec in enumerate(sections):
        name = "".join(c if c.isalnum() or c in "-_" else "-"
                       for c in sec["name"]).strip("-") or f"{prefix}-{i}"
        out = str(Path(out_dir) / f"{take}.{name}.mp4")
        outputs.append(cut_section(styled_mp4, sec, out, reencode=reencode))
    return outputs