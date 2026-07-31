"""cap-tools — unified CLI for Cap screen recording automation and guide generation.

Commands:
    capt record <url> [--beat <name>]     Automate browser-driven recording
    capt guide <project.cap> [--ai]       Turn .cap into illustrated guide
    capt export <project.cap> <out.mp4>   Export .cap to MP4
    capt assemble <manifest.json>         Stitch clips into final video
    capt preflight [url]                  Check all dependencies
    capt config <project.cap> [opts]      Read/write project-config.json
"""

import json
import subprocess
import sys
from pathlib import Path

import click


def _is_wsl() -> bool:
    """True when running inside WSL (Windows Subsystem for Linux)."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


@click.group()
def main():
    """cap-tools: automate recordings and generate guides from Cap .cap files."""
    pass


# ── record ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("url", required=False)
@click.option("--beat", "name", default="full", help="Named beat to record")
@click.option("--out", default="recordings", help="Output directory")
@click.option("--screen", default=None, help="Cap screen ID")
@click.option("--steps", default=None, help="Path to a steps.json file (scripted actions)")
@click.option("--marker-source", default="steps",
              type=click.Choice(["steps", "global-capture", "steps+global-capture"]),
              help="How to collect zoom markers (global-capture is macOS-only)")
@click.option("--export-to", default=None, help="Also export the recording to this MP4 path")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def record(url, name, out, screen, steps, marker_source, export_to, json_out):
    """Automate a browser-driven screen recording with automatic zoom.

    On macOS/Linux, runs in-process (no PowerShell hop). On WSL, invokes the
    beat-runner on Windows via PowerShell, unchanged from before.
    """
    step_list = []
    if steps:
        step_list = json.loads(Path(steps).read_text())

    if _is_wsl():
        _record_via_windows(url, name, out, screen, steps, marker_source, export_to, json_out)
        return

    from capt.record.beat import run_beat

    if json_out:
        click.echo(json.dumps({"type": "Progress", "stage": "recording"}))

    result = run_beat(url, step_list, out, name=name, screen_id=screen,
                      marker_source=marker_source, export_to=export_to)

    if json_out:
        click.echo(json.dumps({
            "type": "Completed",
            "recordingId": result.recording_id,
            "capPath": result.cap_path,
            "events": result.events,
            "zoomSegments": result.zoom_segments,
            "exportPath": result.export_path,
        }))
    else:
        click.echo(f"✓ Beat '{name}' recorded: {result.cap_path}")
        if result.export_path:
            click.echo(f"  Exported: {result.export_path}")


def _record_via_windows(url, name, out, screen, steps, marker_source, export_to, json_out):
    """WSL -> PowerShell -> Windows beat_runner_entry.py, unchanged in spirit
    from the pre-macOS-support implementation."""
    from capt import tailscale

    out_dir = str(Path(out).resolve())
    if url and url.lower().startswith("https://"):
        resolved = tailscale.resolve_target(url)
        if resolved != url:
            if not json_out:
                click.echo(f"→ HTTPS target via Tailscale: {resolved}")
            url = resolved

    ps_cmd = f"cd C:\\cap-tools; python beat_runner_entry.py {name} {url} {out_dir}"
    if screen:
        ps_cmd += f" --screen {screen}"
    if steps:
        ps_cmd += f" --steps {steps}"
    if marker_source and marker_source != "steps":
        ps_cmd += f" --marker-source {marker_source}"
    if export_to:
        ps_cmd += f" --export-to {export_to}"

    if json_out:
        click.echo(json.dumps({"status": "running", "beat": name, "url": url}))

    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=600,
    )

    if proc.returncode != 0:
        err = proc.stderr.strip() or "beat runner failed"
        if json_out:
            click.echo(json.dumps({"status": "error", "error": err}))
        else:
            click.echo(f"✗ {err}", err=True)
        sys.exit(1)

    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        result = {"raw": proc.stdout.strip()}

    if json_out:
        if "raw" in result:
            # Unparseable output is a different, already-handled failure
            # mode — surface it as-is rather than forcing it into the
            # Completed schema below.
            click.echo(json.dumps(result))
        else:
            # Remap the Windows side's snake_case BeatResult fields into the
            # exact same schema the in-process (macOS/Linux) path emits, so
            # a --json consumer sees one shape regardless of platform.
            click.echo(json.dumps({
                "type": "Completed",
                "recordingId": result.get("recording_id"),
                "capPath": result.get("cap_path"),
                "events": result.get("events"),
                "zoomSegments": result.get("zoom_segments"),
                "exportPath": result.get("export_path"),
            }))
    else:
        click.echo(f"✓ Beat '{name}' recorded: {result.get('cap_path', '?')}")


# ── guide ─────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("project_path")
@click.option("--ai", is_flag=True, help="Enable AI step-text generation")
@click.option("--format", "fmt", default="both",
              type=click.Choice(["html", "md", "both"]))
@click.option("--out", default=None, help="Output directory")
@click.option("--transcript", default=None, help="External transcript JSON")
@click.option("--model", default=None, help="LLM model for --ai")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def guide(project_path, ai, fmt, out, transcript, model, json_out):
    """Turn a .cap recording into an illustrated step-by-step guide.

    Pipeline: ingest → (transcribe) → (structure if --ai) → render.
    Deterministic by default; --ai enables LLM step-text generation.
    """
    from capt.guide.pipeline import run_guide

    cap_path = Path(project_path)
    out_dir = out or f"output/{cap_path.stem}"

    if json_out:
        click.echo(json.dumps({"type": "Progress", "stage": "guide"}))

    result = run_guide(str(cap_path), out_dir, ai=ai, transcript_path=transcript,
                       model=model, fmt=fmt)

    if json_out:
        click.echo(json.dumps({"type": "Completed", **result}))
    else:
        click.echo(f"✓ Guide: {result['steps']} steps -> {result['path']}")


# ── export ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("project_path")
@click.argument("output_path")
@click.option("--fps", default=60, type=int)
@click.option("--quality", default="maximum",
              type=click.Choice(["maximum", "social", "web", "potato"]))
@click.option("--resolution", default=None, help="WIDTHxHEIGHT")
@click.option("--json", "json_out", is_flag=True)
def export_cmd(project_path, output_path, fps, quality, resolution, json_out):
    """Export a .cap project to MP4."""
    from capt.export import export
    result = export(project_path, output_path, fps, quality, resolution, json_out)
    if json_out:
        click.echo(json.dumps(result))
    else:
        click.echo(f"Exported: {result['path']}")


# ── assemble ──────────────────────────────────────────────────────────────────

@main.command()
@click.argument("manifest_path")
@click.option("--json", "json_out", is_flag=True)
def assemble(manifest_path, json_out):
    """Assemble beat clips + VO + captions into a final video."""
    from capt.assemble import main as assemble_main
    import sys as _sys
    _sys.argv = ["assemble", manifest_path]
    if json_out:
        _sys.argv.append("--json")
    assemble_main()


# ── preflight ─────────────────────────────────────────────────────────────────

@main.command()
@click.argument("url", required=False)
@click.option("--output-dir", default="recordings")
@click.option("--skip-playwright", is_flag=True)
@click.option("--marker-source", default="steps",
              type=click.Choice(["steps", "global-capture", "steps+global-capture"]),
              help="Include the global-capture permission gate (macOS-only)")
@click.option("--json", "json_out", is_flag=True)
def preflight(url, output_dir, skip_playwright, marker_source, json_out):
    """Check all dependencies before recording."""
    from capt.preflight import preflight as run_preflight
    ok = run_preflight(url, output_dir, require_playwright=not skip_playwright,
                       marker_source=marker_source)
    if json_out:
        click.echo(json.dumps({"ok": ok}))
    sys.exit(0 if ok else 1)


# ── zoom ──────────────────────────────────────────────────────────────────────

@main.group()
def zoom():
    """Build and apply auto-zoom segments from recording-time markers.

    Reference implementation of the "Record a multi-step walkthrough with
    automatic zoom" agent workflow: `zoom mark` collects elapsed-time markers
    while you drive a recording by hand; `zoom apply` turns them into
    timeline.zoomSegments and merges them into the project's existing config.
    """
    pass


@zoom.command("mark")
@click.option("--out", default="events.json", help="Where to write collected markers")
def zoom_mark(out):
    """Interactively collect elapsed-time markers during a recording.

    Starts a timer immediately. Press Enter (optionally typing a label first)
    for each meaningful moment; Ctrl-D finishes and writes the markers to
    --out as a JSON list of {label, elapsed_s}, ready for `capt zoom apply`.
    """
    from capt.zoom import create_tracker

    tracker = create_tracker()
    click.echo("Tracking started. Type a label and press Enter to mark a step.")
    click.echo("Press Enter with no text for an unlabeled mark. Ctrl-D to finish.")
    i = 0
    try:
        while True:
            label = click.prompt("mark", default="", show_default=False, prompt_suffix="> ")
            i += 1
            tracker.mark(label or f"step-{i}")
    except (EOFError, click.exceptions.Abort):
        pass

    events = tracker.events()
    Path(out).write_text(json.dumps(events, indent=2))
    click.echo(f"\n✓ {len(events)} marker(s) written to {out}")


@zoom.command("apply")
@click.argument("project_path")
@click.argument("events_path")
@click.option("--amount", default=2.0, type=float, help="Zoom level (1.5 subtle, 2.0 strong)")
@click.option("--yes", is_flag=True, help="Write without an interactive confirmation")
@click.option("--json", "json_out", is_flag=True)
def zoom_apply(project_path, events_path, amount, yes, json_out):
    """Build zoom segments from markers and merge them into a project's config.

    Reads the project's CURRENT config, builds timeline.zoomSegments from the
    markers in events_path (see `capt zoom mark`), and merges them in —
    `cap project config set` replaces the whole document, so this never
    writes a partial object. Shows the merged zoomSegments and asks for
    confirmation before writing, unless --yes is passed.
    """
    from capt.config import read_config, write_config
    from capt.zoom import build_zoom_segments, merge_zoom_segments

    events = json.loads(Path(events_path).read_text())
    segments = build_zoom_segments(events, amount=amount)

    if not segments:
        click.echo("No markers found — nothing to apply.", err=True)
        sys.exit(1)

    current = read_config(project_path)
    merged = merge_zoom_segments(current, segments)

    if json_out:
        click.echo(json.dumps({"type": "Proposed", "zoomSegments": segments}))
    else:
        click.echo(f"Proposed {len(segments)} zoom segment(s) from {len(events)} marker(s):")
        click.echo(json.dumps(segments, indent=2))

    if not yes:
        if not click.confirm("Write this merged config to the project?"):
            click.echo("Aborted — nothing written.")
            sys.exit(1)

    write_config(project_path, merged)

    if json_out:
        click.echo(json.dumps({"type": "Completed", "path": project_path, "zoomSegments": segments}))
    else:
        click.echo(f"✓ Wrote {len(segments)} zoom segment(s) to {project_path}")


# ── config ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("project_path")
@click.option("--get", "get_config", is_flag=True, help="Read current config")
@click.option("--preset", default=None, type=click.Choice(["demo", "clean", "raw"]),
              help="Apply a preset")
@click.option("--zoom", default=None, help="Path to zoom segments JSON")
@click.option("--json", "json_out", is_flag=True)
def config(project_path, get_config, preset, zoom, json_out):
    """Read or write a .cap project's project-config.json."""
    from capt.config import read_config, write_config, build_config

    if get_config:
        cfg = read_config(project_path)
        click.echo(json.dumps(cfg, indent=2))
    elif preset:
        zoom_segs = None
        if zoom:
            zoom_segs = json.loads(Path(zoom).read_text())
        cfg = build_config(preset=preset, zoom_segments=zoom_segs)
        write_config(project_path, cfg)
        if json_out:
            click.echo(json.dumps({"status": "applied", "preset": preset}))
        else:
            click.echo(f"Applied preset '{preset}' to {project_path}")
    else:
        click.echo("Use --get to read or --preset to apply a preset.")


if __name__ == "__main__":
    main()
