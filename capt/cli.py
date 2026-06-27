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
import sys
from pathlib import Path

import click


@click.group()
def main():
    """cap-tools: automate recordings and generate guides from Cap .cap files."""
    pass


# ── record ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("url")
@click.option("--beat", default=None, help="Named beat to record")
@click.option("--out", default="recordings", help="Output directory")
@click.option("--screen", default=None, help="Cap screen ID")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON output")
def record(url, beat, out, screen, json_out):
    """Automate a browser-driven screen recording.

    Invokes the Windows beat-runner via PowerShell. Beat steps are read from
    a beats.json file or passed via stdin.
    """
    import subprocess

    beat_name = beat or "full"
    out_dir = str(Path(out).resolve())

    # Build PowerShell command
    ps_cmd = (
        f"cd C:\\cap-tools; "
        f"python beat_runner.py {beat_name} {url} {out_dir}"
    )
    if screen:
        ps_cmd += f" --screen {screen}"

    if json_out:
        click.echo(json.dumps({"status": "running", "beat": beat_name, "url": url}))

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

    # Parse result
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        result = {"raw": proc.stdout.strip()}

    if json_out:
        result["status"] = "completed"
        click.echo(json.dumps(result))
    else:
        click.echo(f"✓ Beat '{beat_name}' recorded: {result.get('capProjectPath', '?')}")


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
    from capt.guide.ingest import ingest
    from capt.guide.render import render

    cap_path = Path(project_path)
    out_dir = out or f"output/{cap_path.stem}"

    # Step 1: Ingest
    if json_out:
        click.echo(json.dumps({"type": "Progress", "stage": "ingest"}))
    result = ingest(str(cap_path), out_dir, transcript_path=transcript)

    # Step 2: Structure (if --ai)
    if ai:
        if json_out:
            click.echo(json.dumps({"type": "Progress", "stage": "structure"}))
        from capt.guide.structure import structure
        from capt.guide.transcribe import transcribe

        # Transcribe audio if no transcript provided
        transcript_path = transcript
        if not transcript_path:
            # Try to find audio-input.ogg in the .cap dir
            audio = cap_path / "audio-input.ogg"
            if audio.exists():
                t_out = Path(out_dir) / "transcript.json"
                transcribe(str(audio), out_path=str(t_out))
                transcript_path = str(t_out)

        if transcript_path:
            items_out = Path(out_dir) / "items.json"
            structure(transcript_path, str(items_out), model=model,
                      title=result["title"], recording=result["title"])

    # Step 3: Render
    if json_out:
        click.echo(json.dumps({"type": "Progress", "stage": "render"}))

    # Find display.mp4
    display = cap_path / "display.mp4"
    if not display.exists():
        # Try segments
        meta = json.loads((cap_path / "recording-meta.json").read_text())
        segs = meta.get("segments", [])
        if segs and "display" in segs[0]:
            display = cap_path / segs[0]["display"]["path"]
        elif "display" in meta:
            display = cap_path / meta["display"]["path"]

    items_path = Path(out_dir) / "items.json"
    if items_path.exists():
        render_result = render(str(items_path), str(display), out_dir, fmt=fmt)
    else:
        # No AI — just the ingest output
        render_result = {"html": str(Path(out_dir) / "guide.html"), "md": None}

    if json_out:
        click.echo(json.dumps({
            "type": "Completed",
            "path": out_dir,
            "steps": result["step_count"],
            "html": render_result.get("html"),
            "md": render_result.get("md"),
        }))
    else:
        click.echo(f"✓ Guide: {result['step_count']} steps -> {out_dir}")


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
@click.option("--json", "json_out", is_flag=True)
def preflight(url, output_dir, skip_playwright, json_out):
    """Check all dependencies before recording."""
    from capt.preflight import preflight as run_preflight
    ok = run_preflight(url, output_dir, require_playwright=not skip_playwright)
    if json_out:
        click.echo(json.dumps({"ok": ok}))
    sys.exit(0 if ok else 1)


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
