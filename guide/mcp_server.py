#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.0",
# ]
# ///
"""
mcp_server.py — Guide Tool MCP server

Exposes project state, asset queries, and build operations to Claude in Cowork.
Run alongside the UACS MCP server — these tools cover the file system and build
layer that UACS has no concept of. UACS owns memory (memory.add / memory.search /
add_decision). This server owns everything else.

─────────────────────────────────────────────────────────────────────────────────
Tool surface

  guide_list_projects       List all projects with status
  guide_project_status      Full project state: context, assets, session, corrections
  guide_add_note            Add a note to the current session (writes JSON + UACS)
  guide_list_frames         List available frame files for a project
  guide_get_transcript      Read transcript content for a project
  guide_run_build           Trigger build.py and return output
  guide_run_analyze         Trigger frame extraction on all recordings
  guide_session_primer      Return the full session primer text

─────────────────────────────────────────────────────────────────────────────────
Setup

  Add to Claude Desktop config (~/.claude/claude_desktop_config.json):

    {
      "mcpServers": {
        "guide-tool": {
          "command": "uv",
          "args": ["run", "--script", "/path/to/guide-tool/mcp_server.py"]
        },
        "uacs": {
          "command": "uacs",
          "args": ["serve"]
        }
      }
    }

  The two servers are complementary, not competing. Use UACS tools for memory
  read/write/search. Use guide-tool tools for project state and build operations.
─────────────────────────────────────────────────────────────────────────────────
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ── Paths ──────────────────────────────────────────────────────────────────────

TOOL_DIR = Path(__file__).parent
PROJECTS_DIR = TOOL_DIR / "projects"
GLOBAL_CONFIG = TOOL_DIR / "config.json"

mcp = FastMCP("guide-tool")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_json(path: Path, default=None):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _project_path(name: str) -> Path:
    return PROJECTS_DIR / name


def _require_project(name: str) -> Path:
    p = _project_path(name)
    if not p.exists():
        raise ValueError(f"Project '{name}' not found. Run: uv run guide.py new {name}")
    return p


def _asset_counts(p: Path) -> dict:
    counts = {}
    for subdir in ["recordings", "transcripts", "frames/main", "frames/coverage", "output"]:
        d = p / subdir
        if d.exists():
            files = [f for f in d.glob("*") if not f.name.startswith(".")]
            counts[subdir] = len(files)
        else:
            counts[subdir] = 0
    return counts


def _latest_session(p: Path) -> dict:
    sessions = sorted((p / "sessions").glob("*.json")) if (p / "sessions").exists() else []
    if sessions:
        return _load_json(sessions[-1])
    return {}


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def guide_list_projects() -> str:
    """
    List all guide projects with their current status.

    Returns a JSON array of objects:
      { name, status, last_session, description, asset_counts }

    Status values: "built" | "recorded" | "setup"
    """
    if not PROJECTS_DIR.exists():
        return json.dumps([])

    results = []
    for p in sorted(PROJECTS_DIR.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue

        ctx = _load_json(p / "context.json")
        sessions = sorted((p / "sessions").glob("*.json")) if (p / "sessions").exists() else []
        last = sessions[-1].stem if sessions else None
        assets = _asset_counts(p)

        if assets.get("output", 0) > 0:
            status = "built"
        elif assets.get("recordings", 0) > 0:
            status = "recorded"
        else:
            status = "setup"

        results.append({
            "name": p.name,
            "status": status,
            "last_session": last,
            "description": ctx.get("description", ""),
            "platform": ctx.get("platform", ""),
            "asset_counts": assets,
        })

    return json.dumps(results, indent=2)


@mcp.tool()
def guide_project_status(project_name: str) -> str:
    """
    Return full project state for a named project.

    Includes: context metadata, asset inventory, latest session (focus,
    pending items, re-shoot requests), and corrections history.

    Args:
        project_name: The project directory name (as shown in guide_list_projects)
    """
    p = _require_project(project_name)
    ctx = _load_json(p / "context.json")
    global_cfg = _load_json(GLOBAL_CONFIG)
    session = _latest_session(p)

    # List actual file names per asset dir
    assets = {}
    for subdir in ["recordings", "transcripts", "output"]:
        d = p / subdir
        if d.exists():
            assets[subdir] = [f.name for f in sorted(d.glob("*")) if not f.name.startswith(".")]
        else:
            assets[subdir] = []

    # Frame subdirs
    frames_main = p / "frames" / "main"
    frames_coverage = p / "frames" / "coverage"
    assets["frames/main"] = _list_dir_recursive(frames_main)
    assets["frames/coverage"] = _list_dir_recursive(frames_coverage)

    return json.dumps({
        "project": project_name,
        "path": str(p),
        "context": {
            "description": ctx.get("description", ""),
            "platform": ctx.get("platform", ""),
            "audience": ctx.get("audience", ""),
            "audience_technical_level": ctx.get("audience_technical_level", "intermediate"),
            "output_filename": ctx.get("output_filename", ""),
            "known_terminology": ctx.get("known_terminology", {}),
            "corrections_history": ctx.get("corrections_history", []),
            "parts": ctx.get("parts", []),
            "notes": ctx.get("notes", []),
        },
        "assets": assets,
        "session": {
            "focus": session.get("focus", ""),
            "pending": session.get("pending", []),
            "completed": session.get("completed", []),
            "re_shoot_requests": session.get("re_shoot_requests", []),
            "notes": session.get("notes", []),
            "last_updated": session.get("last_updated", ""),
        },
        "global_style": global_cfg.get("style_preferences", []),
    }, indent=2)


def _list_dir_recursive(path: Path, max_depth=2, _depth=0) -> list:
    """Recursively list files under path up to max_depth."""
    if not path.exists() or _depth > max_depth:
        return []
    results = []
    for f in sorted(path.iterdir()):
        if f.name.startswith("."):
            continue
        if f.is_dir():
            sub = _list_dir_recursive(f, max_depth, _depth + 1)
            if sub:
                results.append({"dir": f.name, "files": sub})
        else:
            results.append(f.name)
    return results


@mcp.tool()
def guide_add_note(project_name: str, note_text: str) -> str:
    """
    Add a note to the current session log for a project.
    Also syncs the note to UACS project memory so it persists across sessions.

    Args:
        project_name: The project directory name
        note_text:    The note to record (e.g. "Advanced tab fires On Enrollment not On Completion")

    Returns confirmation string.
    """
    p = _require_project(project_name)
    sessions = sorted((p / "sessions").glob("*.json")) if (p / "sessions").exists() else []
    if not sessions:
        return f"No session file found for '{project_name}'. Run: uv run guide.py session {project_name}"

    session_path = sessions[-1]
    session = _load_json(session_path)
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "text": note_text}
    session.setdefault("notes", []).append(entry)
    with open(session_path, "w") as f:
        json.dump(session, f, indent=2)

    # Sync to UACS
    _uacs_memory_add(project_name, f"Session note [{_today()}]: {note_text}")

    return f"Note saved to {session_path.name} and synced to UACS."


def _uacs_memory_add(project_name: str, text: str):
    """Write a memory to UACS project scope. Raises on failure."""
    try:
        result = subprocess.run(
            ["uacs", "memory", "add", text, "--scope", f"project:{project_name}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"UACS returned non-zero: {result.stderr.strip() or result.stdout.strip()}"
            )
    except FileNotFoundError:
        raise RuntimeError(
            "uacs not found in PATH. Install: https://github.com/kylebrodeur/universal-agent-context"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("uacs timed out. Is the server running? Start with: uacs serve")


@mcp.tool()
def guide_list_frames(project_name: str, subdir: str = "main") -> str:
    """
    List available frame files for a project.

    Args:
        project_name: The project directory name
        subdir:       "main" (default) or "coverage" — which frames directory to list

    Returns a JSON object mapping subdirectory names to sorted lists of frame filenames.
    Example: { "scene": ["scene_001.jpg", "scene_002.jpg"], "interval": ["1.jpg", "3.jpg"] }
    """
    p = _require_project(project_name)
    frames_dir = p / "frames" / subdir

    if not frames_dir.exists():
        return json.dumps({
            "error": f"No frames/{subdir} directory found. Run: uv run guide.py analyze {project_name}"
        })

    result = {}
    # Two possible layouts: flat (all jpgs in frames/main/) or
    # nested (frames/main/<recording-name>/scene/ and /interval/)
    jpgs_flat = sorted(f.name for f in frames_dir.glob("*.jpg"))
    if jpgs_flat:
        result["frames"] = jpgs_flat
    else:
        for sub in sorted(frames_dir.iterdir()):
            if sub.is_dir():
                for strategy_dir in sorted(sub.iterdir()):
                    if strategy_dir.is_dir():
                        key = f"{sub.name}/{strategy_dir.name}"
                        result[key] = sorted(f.name for f in strategy_dir.glob("*.jpg"))
                    elif strategy_dir.suffix == ".jpg":
                        result.setdefault(sub.name, []).append(strategy_dir.name)

    if not result:
        return json.dumps({"error": f"No .jpg files found in frames/{subdir}/. Run analyze first."})

    return json.dumps(result, indent=2)


@mcp.tool()
def guide_get_transcript(project_name: str, filename: str | None = None) -> str:
    """
    Read transcript content for a project.

    Args:
        project_name: The project directory name
        filename:     Optional — specific transcript filename (e.g. "recording.json").
                      If omitted, returns the first transcript found.

    Returns the transcript as a JSON string with segments including start/end times and text.
    """
    p = _require_project(project_name)
    transcripts_dir = p / "transcripts"

    if not transcripts_dir.exists() or not any(transcripts_dir.glob("*.json")):
        return json.dumps({"error": f"No transcripts found in {transcripts_dir}"})

    if filename:
        target = transcripts_dir / filename
    else:
        target = sorted(transcripts_dir.glob("*.json"))[0]

    if not target.exists():
        return json.dumps({"error": f"File not found: {target}"})

    data = _load_json(target)

    # Normalize: support both flat array and {segments: [...]} formats
    segments = data.get("segments", data if isinstance(data, list) else [])

    # Return a simplified view: timestamp + text for each segment
    simplified = []
    for seg in segments:
        start = seg.get("start", 0)
        m, s = divmod(start, 60)
        simplified.append({
            "timestamp": f"{int(m)}:{s:05.2f}",
            "start_sec": seg.get("start"),
            "end_sec": seg.get("end"),
            "text": seg.get("text", "").strip(),
        })

    return json.dumps({
        "file": target.name,
        "duration": data.get("duration"),
        "segment_count": len(simplified),
        "segments": simplified,
    }, indent=2)


@mcp.tool()
def guide_run_build(project_name: str) -> str:
    """
    Trigger the project's build.py script to regenerate the HTML guide.

    Runs build.py in the project directory and returns stdout/stderr.
    The guide is written to projects/<name>/output/.

    Args:
        project_name: The project directory name
    """
    p = _require_project(project_name)
    build_script = p / "build.py"

    if not build_script.exists():
        return (
            f"No build.py found at {build_script}.\n"
            "Create one from the html_builder_template.py in the video-to-html-guide skill."
        )

    result = subprocess.run(
        [sys.executable, str(build_script)],
        cwd=str(p),
        capture_output=True,
        text=True,
        timeout=120,
    )

    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
    status = "✅ Build succeeded." if result.returncode == 0 else "❌ Build failed."

    return f"{status}\n\n{output.strip()}"


@mcp.tool()
def guide_run_analyze(project_name: str) -> str:
    """
    Run guide.py analyze for a project — extracts frames from all recordings
    using both scene-detection and interval strategies.

    This is a long-running operation (30–120s depending on video length).
    Returns the combined stdout output.

    Args:
        project_name: The project directory name
    """
    guide_py = TOOL_DIR / "guide.py"
    if not guide_py.exists():
        return f"guide.py not found at {guide_py}"

    result = subprocess.run(
        ["uv", "run", str(guide_py), "analyze", project_name],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(TOOL_DIR),
    )

    output = result.stdout + ("\n" + result.stderr if result.stderr else "")
    return output.strip()


@mcp.tool()
def guide_session_primer(project_name: str) -> str:
    """
    Return the full session primer text for a project.

    The primer is a human-readable summary of all project context:
    platform, audience, terminology, corrections, pending work, assets.
    Useful for reviewing the full state of a project in one call.

    Note: UACS auto-injects the memory version of this context at session start.
    Use this tool when you need the structured, file-system-aware version —
    e.g. to check which recordings are present or what the pending work is.

    Args:
        project_name: The project directory name
    """
    guide_py = TOOL_DIR / "guide.py"
    if not guide_py.exists():
        return f"guide.py not found at {guide_py}"

    result = subprocess.run(
        ["uv", "run", str(guide_py), "session", project_name],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(TOOL_DIR),
    )

    return result.stdout.strip()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
