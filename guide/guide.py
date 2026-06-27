#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "rich>=13.0",
# ]
# ///
"""
guide.py — Personal guide-creation CLI
Manages projects, context, recordings, and guide generation.
The AI work happens in Claude Cowork/Code. This tool handles everything else.

Usage:
  uv run guide.py install                    Register UACS + guide-tool MCP in Claude Desktop & Code
  uv run guide.py new <project-name>         Create a new project
  uv run guide.py list                       List all projects
  uv run guide.py status <project-name>      Show project status + what's missing
  uv run guide.py analyze <project-name>     Extract frames + parse transcript
  uv run guide.py build <project-name>       Run the HTML build script
  uv run guide.py session <project-name>     Print the full session primer
  uv run guide.py note <project-name> <text> Add a note + sync to UACS memory
  uv run guide.py sync <project-name>        Push full project context to UACS memory
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich import print as rprint

console = Console()

# ── Paths ─────────────────────────────────────────────────────────────────────

TOOL_DIR = Path(__file__).parent
PROJECTS_DIR = TOOL_DIR / "projects"
GLOBAL_CONFIG = TOOL_DIR / "config.json"
SKILLS_DIR = TOOL_DIR / ".." / ".." / ".skills" / "skills" / "video-to-html-guide"  # adjust as needed

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path, default=None):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default or {}

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return data

def today():
    return datetime.now().strftime("%Y-%m-%d")

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def project_path(name):
    return PROJECTS_DIR / name

def require_project(name):
    p = project_path(name)
    if not p.exists():
        print(f"Error: project '{name}' not found. Run: guide.py new {name}")
        sys.exit(1)
    return p

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_install(dry_run: bool = False):
    """
    Register UACS and guide-tool MCP servers in Claude Desktop and Claude Code.

    Writes into:
      - Claude Desktop: platform-specific claude_desktop_config.json
      - Claude Code:    ~/.claude.json  (global MCP config)

    Also tries `claude mcp add` for Claude Code if the CLI is on PATH.

    Pass --dry-run to preview changes without writing anything.
    """

    mcp_server = (TOOL_DIR / "mcp_server.py").resolve()

    # MCP server definitions
    servers = {
        "uacs": {
            "command": "uacs",
            "args": ["serve"],
            "description": "UACS — memory, context injection, semantic search",
        },
        "guide-tool": {
            "command": "uv",
            "args": ["run", str(mcp_server)],
            "description": "Guide Tool — project state, frames, transcripts, build triggers",
        },
    }

    console.rule("[bold cyan]Guide Tool MCP Install[/bold cyan]")

    # Verify prerequisites
    _check_prereqs(servers)

    # --- Claude Desktop -------------------------------------------------------
    desktop_config = _claude_desktop_config_path()
    if desktop_config:
        console.print(f"\n[bold]Claude Desktop config:[/bold] [cyan]{desktop_config}[/cyan]")
        _install_into_json_config(desktop_config, servers, dry_run)
    else:
        console.print("\n[yellow]Claude Desktop config not found.[/yellow] "
                      "Install Claude Desktop or create the config file manually.")

    # --- Claude Code ----------------------------------------------------------
    console.print(f"\n[bold]Claude Code config:[/bold] [cyan]~/.claude.json[/cyan]")

    # Try `claude mcp add` CLI first — it's the idiomatic way
    claude_cli = shutil.which("claude")
    if claude_cli:
        _install_via_claude_cli(servers, dry_run)
    else:
        # Fall back to direct JSON edit of ~/.claude.json
        code_config = Path.home() / ".claude.json"
        _install_into_json_config(code_config, servers, dry_run)

    # --- Summary --------------------------------------------------------------
    console.rule()
    if dry_run:
        console.print("[yellow]Dry run — no files were written.[/yellow] "
                      "Re-run without --dry-run to apply.")
    else:
        console.print(
            "\n[bold green]✅ MCP servers registered.[/bold green]\n"
            "Restart Claude Desktop and Claude Code to pick up the changes.\n\n"
            "[bold]In Claude Code:[/bold]\n"
            "  [cyan]claude mcp list[/cyan]   — verify servers are registered\n"
            "  [cyan]uacs serve[/cyan]         — start the UACS server (if not running)\n\n"
            "[bold]In Cowork:[/bold] UACS loads project memory automatically at session start.\n"
            "Guide-tool tools (guide_list_projects, guide_project_status, etc.) "
            "are available on demand."
        )


def _claude_desktop_config_path() -> Path | None:
    """Return the platform-appropriate Claude Desktop config path, or None if not found."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Claude"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude"
    else:  # Linux / other
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Claude"

    config = base / "claude_desktop_config.json"
    # Return path even if file doesn't exist yet — we'll create it
    if base.exists() or config.exists():
        return config
    return None


def _check_prereqs(servers: dict):
    """Print a preflight check table for each required binary."""
    table = Table(title="Preflight check", show_header=True, border_style="blue")
    table.add_column("Binary", style="cyan")
    table.add_column("Found", justify="center")
    table.add_column("Path")

    all_ok = True
    for name, cfg in servers.items():
        binary = cfg["command"]
        path = shutil.which(binary)
        if path:
            table.add_row(binary, "[green]✓[/green]", path)
        else:
            table.add_row(binary, "[red]✗[/red]", "[red]not in PATH[/red]")
            all_ok = False

    console.print(table)

    if not all_ok:
        console.print("\n[red]Some required binaries are missing from PATH.[/red]")
        if not shutil.which("uacs"):
            console.print("  Install UACS: [cyan]https://github.com/kylebrodeur/universal-agent-context[/cyan]")
            console.print("  Then run:     [cyan]uv sync[/cyan]  (inside the uacs directory)")
        console.print(
            "\n  After installing, re-run: [yellow]uv run guide.py install[/yellow]\n"
            "  The config entries will still be written — you just need the binaries "
            "available before starting a Claude session."
        )


def _install_into_json_config(config_path: Path, servers: dict, dry_run: bool):
    """Merge server definitions into a JSON MCP config file (Claude Desktop or ~/.claude.json)."""
    # Load existing config (or start fresh)
    if config_path.exists():
        try:
            with open(config_path) as f:
                config = json.load(f)
        except json.JSONDecodeError:
            console.print(f"  [yellow]⚠ Could not parse {config_path} — will create a clean copy.[/yellow]")
            config = {}
    else:
        config = {}

    existing_servers = config.setdefault("mcpServers", {})
    added = []
    skipped = []

    for name, cfg in servers.items():
        entry = {"command": cfg["command"], "args": cfg["args"]}
        if name in existing_servers:
            if existing_servers[name] == entry:
                skipped.append(name)
            else:
                # Already present but different — update it
                existing_servers[name] = entry
                added.append(f"{name} [dim](updated)[/dim]")
        else:
            existing_servers[name] = entry
            added.append(name)

    if skipped:
        console.print(f"  [dim]Already registered (unchanged): {', '.join(skipped)}[/dim]")
    if added:
        for name in added:
            console.print(f"  [green]+[/green] {name}  →  {servers[name.split(' ')[0]]['command']} {' '.join(servers[name.split(' ')[0]]['args'])}")

    if not dry_run and added:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        console.print(f"  [green]✅ Written to {config_path}[/green]")
    elif dry_run and added:
        console.print(f"  [yellow](dry run) Would write {len(added)} change(s) to {config_path}[/yellow]")
        preview = json.dumps({"mcpServers": {k: {"command": v["command"], "args": v["args"]} for k, v in servers.items()}}, indent=2)
        console.print(Syntax(preview, "json", theme="monokai", line_numbers=False))


def _install_via_claude_cli(servers: dict, dry_run: bool):
    """Use `claude mcp add` to register servers with Claude Code."""
    for name, cfg in servers.items():
        cmd = ["claude", "mcp", "add", name, cfg["command"]] + cfg["args"]
        console.print(f"  [cyan]{'(dry-run) ' if dry_run else ''}$ {' '.join(cmd)}[/cyan]")
        if not dry_run:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                console.print(f"  [green]✓ {name}[/green]")
            elif "already exists" in (result.stdout + result.stderr).lower():
                console.print(f"  [dim]Already registered: {name}[/dim]")
            else:
                # Non-fatal — fall back to JSON edit
                console.print(f"  [yellow]claude mcp add failed for '{name}': "
                               f"{result.stderr.strip() or result.stdout.strip()}[/yellow]")
                console.print("  [dim]Falling back to direct ~/.claude.json edit…[/dim]")
                code_config = Path.home() / ".claude.json"
                _install_into_json_config(code_config, {name: cfg}, dry_run)


def cmd_new(name):
    """Scaffold a new guide project."""
    p = project_path(name)
    if p.exists():
        console.print(f"[red]Project '{name}' already exists at {p}[/red]")
        sys.exit(1)

    # Create folder structure
    for subdir in ["recordings", "transcripts", "frames/main", "frames/coverage", "output", "sessions"]:
        (p / subdir).mkdir(parents=True)

    # Project context file
    context = {
        "name": name,
        "created": now_iso(),
        "description": "",
        "platform": "",
        "audience": "",
        "audience_technical_level": "intermediate",
        "known_terminology": {},
        "output_filename": f"{name}-guide.html",
        "parts": [],
        "notes": [],
        "corrections_history": []
    }
    save_json(p / "context.json", context)

    # Empty build script placeholder
    build_script = p / "build.py"
    build_script.write_text(
        f"# Auto-generated build script for project: {name}\n"
        f"# Run: python3 build.py\n"
        f"# See video-to-html-guide skill for template.\n\n"
        f"import sys\nsys.path.insert(0, '{SKILLS_DIR}/scripts')\n\n"
        f"# TODO: populate imgs dict and BODY from html_builder_template.py\n"
    )

    # Initial session log
    session = {
        "date": today(),
        "started": now_iso(),
        "focus": "Project setup",
        "completed": [],
        "pending": ["Add project description and context", "Record master video", "Export transcript"],
        "notes": [],
        "re_shoot_requests": []
    }
    save_json(p / "sessions" / f"{today()}.json", session)

    console.print(f"\n[bold green]✅ Project '{name}' created[/bold green] at {p}")
    console.print(Panel(
        f"[bold]1.[/bold] Edit context:    [cyan]{p}/context.json[/cyan]\n"
        f"[bold]2.[/bold] Add recordings:  [cyan]{p}/recordings/[/cyan]\n"
        f"[bold]3.[/bold] Add transcripts: [cyan]{p}/transcripts/[/cyan]\n"
        f"[bold]4.[/bold] Analyze:         [yellow]uv run guide.py analyze {name}[/yellow]\n"
        f"[bold]5.[/bold] Sync to UACS:    [yellow]uv run guide.py sync {name}[/yellow]\n"
        f"[bold]6.[/bold] Start UACS:      [yellow]uacs serve[/yellow]  (if not already running)\n"
        f"[bold]7.[/bold] Open Cowork — context loads automatically at session start",
        title="Next steps", border_style="green"
    ))


def cmd_list():
    """List all projects with brief status."""
    if not PROJECTS_DIR.exists() or not any(PROJECTS_DIR.iterdir()):
        console.print("[yellow]No projects found.[/yellow] Run: [cyan]uv run guide.py new <name>[/cyan]")
        return

    table = Table(title="Guide Projects", border_style="blue", show_lines=False)
    table.add_column("Project", style="bold cyan", min_width=25)
    table.add_column("Status", min_width=12)
    table.add_column("Last Session", style="dim", min_width=14)
    table.add_column("Description", style="white")

    for p in sorted(PROJECTS_DIR.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        ctx = load_json(p / "context.json")
        sessions = sorted((p / "sessions").glob("*.json")) if (p / "sessions").exists() else []
        last = sessions[-1].stem if sessions else "—"
        recordings = len(list((p / "recordings").glob("*.mp4"))) if (p / "recordings").exists() else 0
        output = len(list((p / "output").glob("*.html"))) if (p / "output").exists() else 0
        if output > 0:
            status = Text("● built", style="bold green")
        elif recordings > 0:
            status = Text("● recorded", style="bold yellow")
        else:
            status = Text("○ setup", style="dim")
        table.add_row(p.name, status, last, ctx.get("description", "")[:50])

    console.print(table)


def cmd_status(name):
    """Show detailed project status."""
    p = require_project(name)
    ctx = load_json(p / "context.json")

    console.print(Panel(
        f"[bold]Description:[/bold]  {ctx.get('description') or '[dim](not set — edit context.json)[/dim]'}\n"
        f"[bold]Platform:[/bold]     {ctx.get('platform') or '[dim](not set)[/dim]'}\n"
        f"[bold]Audience:[/bold]     {ctx.get('audience') or '[dim](not set)[/dim]'} "
        f"[dim]({ctx.get('audience_technical_level', 'intermediate')})[/dim]\n"
        f"[bold]Output:[/bold]       [cyan]{ctx.get('output_filename')}[/cyan]",
        title=f"[bold cyan]{name}[/bold cyan]",
        border_style="cyan"
    ))

    # Assets table
    asset_table = Table(show_header=False, box=None, padding=(0, 2))
    asset_table.add_column("Dir", style="dim", min_width=22)
    asset_table.add_column("Count", justify="right")
    asset_table.add_column("Files", style="dim")
    for subdir in ["recordings", "transcripts", "frames/main", "frames/coverage", "output"]:
        d = p / subdir
        files = [f for f in (d.glob("*") if d.exists() else []) if not f.name.startswith(".")]
        sample = ", ".join(f.name for f in files[:3]) + ("…" if len(files) > 3 else "")
        color = "green" if files else "dim"
        asset_table.add_row(subdir, f"[{color}]{len(files)}[/{color}]", sample)
    console.print(Panel(asset_table, title="Assets", border_style="blue"))

    # Latest session
    sessions = sorted((p / "sessions").glob("*.json")) if (p / "sessions").exists() else []
    if sessions:
        latest = load_json(sessions[-1])
        lines = [f"[bold]Date:[/bold]  {sessions[-1].stem}   [bold]Focus:[/bold] {latest.get('focus', '—')}"]
        if latest.get("pending"):
            lines.append("\n[bold yellow]Pending:[/bold yellow]")
            for item in latest["pending"]:
                lines.append(f"  [yellow]•[/yellow] {item}")
        if latest.get("re_shoot_requests"):
            lines.append("\n[bold red]Re-shoots needed:[/bold red]")
            for item in latest["re_shoot_requests"]:
                lines.append(f"  [red]⚠[/red]  {item}")
        console.print(Panel("\n".join(lines), title="Latest Session", border_style="yellow"))

    if ctx.get("corrections_history"):
        lines = []
        for c in ctx["corrections_history"][-3:]:
            lines.append(f"  [dim]{c.get('date','')}[/dim]  {c.get('description','')}")
        console.print(Panel("\n".join(lines), title=f"Corrections History ({len(ctx['corrections_history'])} total)", border_style="dim"))


def cmd_analyze(name):
    """Extract frames from recordings and parse transcripts."""
    p = require_project(name)

    recordings = list((p / "recordings").glob("*.mp4"))
    if not recordings:
        print(f"No .mp4 files found in {p}/recordings/")
        print("Add your recordings and re-run.")
        sys.exit(1)

    script = SKILLS_DIR / "scripts" / "extract_frames.py"
    if not script.exists():
        # Try relative to this file
        script = TOOL_DIR.parent / "video-to-html-guide" / "scripts" / "extract_frames.py"
    if not script.exists():
        print(f"Warning: extract_frames.py not found at {script}")
        print("Run frame extraction manually.")
        return

    for rec in recordings:
        label = rec.stem
        out_dir = p / "frames" / "main" / label
        print(f"\n→ Extracting frames from {rec.name}")
        # Scene detection pass
        print(f"  Scene detection → {out_dir}/scene/")
        subprocess.run([sys.executable, str(script), "scene", str(rec), str(out_dir / "scene")], check=False)
        # 2-second interval pass
        print(f"  Interval (2s) → {out_dir}/interval/")
        subprocess.run([sys.executable, str(script), "interval", str(rec), str(out_dir / "interval"), "--every", "2"], check=False)

    # Parse any transcripts
    transcripts = list((p / "transcripts").glob("*.json"))
    if transcripts:
        print(f"\n→ Parsing {len(transcripts)} transcript(s):")
        for t in transcripts:
            print(f"\n  [{t.name}]")
            _print_transcript(t)
    else:
        print(f"\nNo transcripts found in {p}/transcripts/ — add your Whisper JSON files.")

    _update_session(p, completed=["Frame extraction"], pending=["Review frames", "Select best frame per step", "Run: guide.py build " + name])
    print(f"\n✅ Analysis complete. Review frames in {p}/frames/")
    print(f"   Sync any new context: uv run guide.py sync {name}")
    print(f"   Then open Cowork — UACS will load the project context automatically.")


def _print_transcript(path):
    data = load_json(path)
    segments = data.get("segments", data if isinstance(data, list) else [])
    for seg in segments:
        start = seg.get("start", 0)
        m, s = divmod(start, 60)
        text = seg.get("text", "").strip()
        if text:
            print(f"    [{int(m)}:{s:04.1f}]  {text}")


def cmd_build(name):
    """Run the project's build.py to regenerate the HTML guide."""
    p = require_project(name)
    build_script = p / "build.py"
    if not build_script.exists():
        print(f"No build.py found at {build_script}")
        print("Create one using the html_builder_template.py from the video-to-html-guide skill.")
        sys.exit(1)

    print(f"→ Building guide for project '{name}'...")
    result = subprocess.run([sys.executable, str(build_script)], cwd=str(p))
    if result.returncode == 0:
        _update_session(p, completed=["Guide built"])
        print(f"✅ Done. Output in {p}/output/")
    else:
        print("❌ Build failed. Check build.py for errors.")


def cmd_session(name):
    """Print the full session primer for this project (also saved to sessions/primer-YYYY-MM-DD.txt)."""
    p = require_project(name)
    ctx = load_json(p / "context.json")
    global_cfg = load_json(GLOBAL_CONFIG)

    # Get latest session info
    sessions = sorted((p / "sessions").glob("*.json")) if (p / "sessions").exists() else []
    latest_session = load_json(sessions[-1]) if sessions else {}

    # Get asset inventory
    recordings = [f.name for f in (p / "recordings").glob("*.mp4")] if (p / "recordings").exists() else []
    transcripts = [f.name for f in (p / "transcripts").glob("*.json")] if (p / "transcripts").exists() else []
    frame_dirs = [f.name for f in (p / "frames" / "main").iterdir()] if (p / "frames" / "main").exists() else []
    outputs = [f.name for f in (p / "output").glob("*.html")] if (p / "output").exists() else []

    primer = f"""
=== GUIDE PROJECT CONTEXT — {name} ===
Paste this at the start of your Cowork session.

## Project
- Name: {name}
- Description: {ctx.get('description') or '(not set — update context.json)'}
- Platform: {ctx.get('platform') or '(not set)'}
- Audience: {ctx.get('audience') or '(not set)'} ({ctx.get('audience_technical_level', 'intermediate')} technical level)
- Output file: {p}/output/{ctx.get('output_filename')}

## Assets on disk
- Recordings:  {', '.join(recordings) if recordings else 'none'}
- Transcripts: {', '.join(transcripts) if transcripts else 'none'}
- Frame dirs:  {', '.join(frame_dirs) if frame_dirs else 'none (run: guide.py analyze {name})'}
- Built guides: {', '.join(outputs) if outputs else 'none yet'}

## Build script
- Location: {p}/build.py

## Session context (as of {today()})
- Focus: {latest_session.get('focus', 'not set')}
- Pending: {json.dumps(latest_session.get('pending', []))}
- Re-shoots needed: {json.dumps(latest_session.get('re_shoot_requests', []))}

## Known terminology / corrections
{json.dumps(ctx.get('known_terminology', {}), indent=2)}

## Corrections history (last 3)
{json.dumps(ctx.get('corrections_history', [])[-3:], indent=2)}

## Guide structure / parts
{json.dumps(ctx.get('parts', []), indent=2)}

## Notes
{json.dumps(ctx.get('notes', []), indent=2)}

## Global preferences
{json.dumps(global_cfg, indent=2)}

=== END CONTEXT ===
""".strip()

    print(primer)

    # Also write to a file for easy access
    primer_file = p / "sessions" / f"primer-{today()}.txt"
    primer_file.write_text(primer)
    print(f"\n(Also saved to {primer_file})")

    # Update session timestamp
    _update_session(p)


def cmd_note(name, text):
    """Add a note to the current session log and optionally sync to UACS."""
    p = require_project(name)
    sessions = sorted((p / "sessions").glob("*.json")) if (p / "sessions").exists() else []
    if not sessions:
        console.print("[yellow]No session found.[/yellow] Run: [cyan]uv run guide.py session {name}[/cyan]")
        return
    session = load_json(sessions[-1])
    note_entry = {"time": now_iso(), "text": text}
    session.setdefault("notes", []).append(note_entry)
    save_json(sessions[-1], session)
    console.print(f"[green]✅ Note saved:[/green] {text}")

    # Sync note to UACS project memory
    uacs_memory_add(name, f"Session note [{today()}]: {text}")


def cmd_sync(name):
    """Push full project context to UACS memory (project scope)."""
    p = require_project(name)
    ctx = load_json(p / "context.json")
    global_cfg = load_json(GLOBAL_CONFIG)

    console.print(f"[bold]Syncing project [cyan]{name}[/cyan] to UACS memory...[/bold]")

    memories = []

    # Core identity
    if ctx.get("description"):
        memories.append(f"Guide project '{name}': {ctx['description']}")
    if ctx.get("platform"):
        memories.append(f"Platform being documented: {ctx['platform']}")
    if ctx.get("audience"):
        memories.append(f"Target audience: {ctx['audience']} ({ctx.get('audience_technical_level', 'intermediate')} technical level)")

    # Known terminology
    for term, definition in ctx.get("known_terminology", {}).items():
        memories.append(f"Terminology — '{term}': {definition}")

    # Corrections history
    for correction in ctx.get("corrections_history", []):
        memories.append(f"Past correction [{correction.get('date','')}]: {correction.get('description','')} (in: {correction.get('affected_section','')})")

    # Notes
    for note in ctx.get("notes", []):
        memories.append(f"Project note: {note}")

    # Global style preferences
    for pref in global_cfg.get("style_preferences", []):
        memories.append(f"Style preference (global): {pref}")

    if not memories:
        console.print("[yellow]Nothing to sync — fill in context.json first.[/yellow]")
        return

    # Write to UACS
    success = 0
    for memory in memories:
        if uacs_memory_add(name, memory, verbose=False):
            success += 1

    if success == len(memories):
        console.print(f"[green]✅ Synced {success} memories to UACS project scope.[/green]")
        console.print("[dim]Claude in Cowork will now load this context automatically at session start.[/dim]")
    else:
        console.print(f"[red]⚠ Only {success}/{len(memories)} memories written — UACS may have encountered errors above.[/red]")
        sys.exit(1)


def uacs_memory_add(project_name, text, verbose=True):
    """Write a memory to UACS project scope. Raises on failure."""
    try:
        result = subprocess.run(
            ["uacs", "memory", "add", text, "--scope", f"project:{project_name}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            if verbose:
                console.print(f"[dim green]→ UACS: {text[:60]}{'…' if len(text) > 60 else ''}[/dim green]")
            return True
        else:
            console.print(f"[red]UACS error:[/red] {result.stderr.strip() or result.stdout.strip() or 'non-zero exit'}")
            return False
    except FileNotFoundError:
        console.print("[red]UACS not found.[/red] Install it: [cyan]uv sync[/cyan] inside the uacs directory, then add it to your PATH.")
        console.print("Repository: https://github.com/kylebrodeur/universal-agent-context")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]UACS timed out.[/red] Is the server running? Start it with: [cyan]uacs serve[/cyan]")
        sys.exit(1)


def _update_session(p, completed=None, pending=None):
    """Update the latest session log with completed/pending items."""
    sessions = sorted((p / "sessions").glob("*.json")) if (p / "sessions").exists() else []
    if not sessions:
        return
    session = load_json(sessions[-1])
    session["last_updated"] = now_iso()
    if completed:
        session.setdefault("completed", []).extend(completed)
    if pending:
        existing = session.get("pending", [])
        for item in pending:
            if item not in existing:
                existing.append(item)
        session["pending"] = existing
    save_json(sessions[-1], session)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Guide Tool CLI — manage screen-recording guide projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="Register UACS + guide-tool MCP in Claude Desktop & Code")
    p_install.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    sub.add_parser("list",   help="List all projects")
    p_new     = sub.add_parser("new",     help="Create a new project")
    p_status  = sub.add_parser("status",  help="Show project status")
    p_analyze = sub.add_parser("analyze", help="Extract frames + parse transcript")
    p_build   = sub.add_parser("build",   help="Run the HTML build script")
    p_session = sub.add_parser("session", help="Print the full session primer for this project")
    p_note    = sub.add_parser("note",    help="Add a note to current session + sync to UACS")
    p_sync    = sub.add_parser("sync",    help="Push full project context to UACS memory")

    for p in [p_new, p_status, p_analyze, p_build, p_session, p_sync]:
        p.add_argument("project", help="Project name")
    p_note.add_argument("project")
    p_note.add_argument("text", help="Note text")

    args = parser.parse_args()

    if   args.command == "install": cmd_install(dry_run=getattr(args, "dry_run", False))
    elif args.command == "new":     cmd_new(args.project)
    elif args.command == "list":    cmd_list()
    elif args.command == "status":  cmd_status(args.project)
    elif args.command == "analyze": cmd_analyze(args.project)
    elif args.command == "build":   cmd_build(args.project)
    elif args.command == "session": cmd_session(args.project)
    elif args.command == "note":    cmd_note(args.project, args.text)
    elif args.command == "sync":    cmd_sync(args.project)


if __name__ == "__main__":
    main()
