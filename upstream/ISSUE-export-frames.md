<!--
POSTED 2026-07-31: https://github.com/CapSoftware/Cap/issues/2059
Kept here as the source record. Not yet shared in Cap's Discord — do that
per CONTRIBUTING.md and link the thread back into the issue when it happens.
-->

**[feature request] native frame-at-timestamp export (no external ffmpeg dependency for downstream tools)**

### Problem
`cap export` already renders a full video natively, but there's no way to pull
a single still frame at a given timestamp (or read a segment's exact duration)
without shelling out to a separately-installed `ffmpeg`/`ffprobe`. Any tool
built on top of Cap that needs still frames — thumbnailing, a step-by-step
doc generator, a diffing/QA tool — ends up carrying that whole external
dependency itself, with all its fragility: PATH lookup, version drift,
platform-specific installs, and (what actually happened to us) a Homebrew
library-version mismatch silently breaking frame extraction with no clear
error.

### Concrete case
cap-tools (a Python CLI built on Cap) has a `capt guide` command that
extracts a screenshot per detected click from a `.cap` recording's
`display.mp4`. It shelled out to `ffmpeg -ss <t> -i display.mp4 -vframes 1`
per click and `ffprobe` for segment duration. On 2026-07-31, a routine
`brew upgrade` on a dev machine left the installed `ffmpeg` linked against a
now-missing `libSvtAv1Enc.3.dylib`, and every call silently produced zero
frames — the tool's own error handling didn't even catch it as an ffmpeg
problem, since `subprocess.run` still spawns the process, it just exits
non-zero. The realistic fix for us was vendoring
[PyAV](https://pyav.org/) (FFmpeg statically compiled into the Python
wheel) to remove the external dependency entirely — but that's real
duplicated effort (and duplicated FFmpeg-linking risk) that every Cap-based
tool has to solve independently, when Cap's own CLI already has a native,
often hardware-accelerated decode path (`cap export --force-ffmpeg-decoder`
exists specifically as an *opt-out* of the platform decoder, implying the
default path isn't shelling out to system ffmpeg at all).

### Proposal
Add a way to pull one or more still frames — and/or just a duration query —
through the same native pipeline `cap export` already uses, so no consumer
of Cap recordings needs its own vendored or system video toolchain just to
get a thumbnail.

```
cap export <project.cap> --frames-at 3.5,7.2,12.0 --out-dir frames/ --json
cap project duration <project.cap> --json   # or fold into `project validate`'s existing output
```

- Frame output could reuse `--format`'s existing container knowledge (jpg/png)
  and `--resolution` for downscaling — same flags as `cap export` already has.
- Duration is probably the cheaper win alone: `cap project validate` already
  reads the project; adding a `durationSeconds` field to its JSON output would
  let tools drop `ffprobe` even without full frame-export support.

### Why now
Cap's CLI surface is clearly meant to be the foundation other tools build on
(`cap agents install`, the MCP server, the whole "designed to be driven by
automation and AI agents" framing in `cap --help`). Every downstream tool
that wants a still frame currently has to solve the exact fragility we just
hit, independently, on their own.

### Status
No PR yet — wanted to check appetite and naming/shape preference first.
Happy to prototype against `crates/export` if this is a direction you'd take
a contribution on.

### Maintainer response (2026-07-31)
Corrections/context from a Cap maintainer on the posted issue — most of
what's proposed above already exists natively; the real gap is CLI surface
and discoverability, not a missing capability:

- **Frame-at-timestamp already works**: `cap export-preview <path.cap>
  --frame-time <f64> --settings-json '...'` renders one still frame through
  the exact same native pipeline as `cap export` (`ExporterBase`, same
  decoders, `FrameRenderer::render_immediate`), encodes to JPEG, and returns
  it as base64 in `ExportPreviewResult.jpeg_base64` on stdout. Impl:
  `render_preview` in `crates/export/src/preview.rs`; CLI arg in
  `apps/cli/src/export.rs`.
- **Duration is already computed natively too**: `cap_rendering::get_duration`
  (`crates/rendering/src/lib.rs:1844`) reads it via the Rust FFmpeg *library*
  bindings (`ffmpeg::format::input`), never a system `ffprobe` subprocess.
  `ExportPreviewResult.total_frames` already derives from it.
- **`--force-ffmpeg-decoder` confirmed**: selects the in-process FFmpeg
  software decoder vs. the platform hardware decoder (AVAssetReader/
  MediaFoundation), with automatic fallback to FFmpeg on hardware-decode
  failure (`decoder/mod.rs:628`) — both paths go through `cap_video_decode`,
  neither ever shells out to a separate system ffmpeg/ffprobe binary. The
  fragility this issue describes is specific to going *around* Cap's own
  pipeline to call system ffmpeg directly — exactly what this feature would
  let downstream tools stop doing.
- **What's actually missing**, and would make a clean, scoped PR:
  1. `export-preview` returns base64 on stdout, not files to `--out-dir`
     (thin layer on `render_preview`).
  2. One frame per invocation, no batch `--frames-at a,b,c` — and
     `render_preview` rebuilds the heavy `ExporterBase` (wgpu device/adapter
     + decoder spawn) per call, so a batch mode needs to build once and loop
     `render_preview_with_base` per timestamp.
  3. Requires `--settings-json` instead of the friendly `--format`/
     `--resolution`/`--quality` flags `cap export` already exposes —
     `settings_from_flags` in `export.rs` is the pattern to copy.
  4. Not listed in `cap guide --json` (the agent capability manifest) —
     `export-preview` is undiscoverable to agents today. Maintainer flagged
     this as probably the single highest-value fix on its own.
- **Suggested scope split** (maintainer's own framing): (1) add
  `durationSeconds` to `project validate`/`inspect` JSON + document
  `export-preview` in `cap guide` — small, high-leverage, unblocks dropping
  `ffprobe`/`ffmpeg` immediately for any downstream tool; (2) the batch
  frame-files export mode in `crates/export` — bigger, separate PR.

**Implication for cap-tools itself**: `capt guide`'s PyAV vendoring (see
`capt/guide/ingest.py`) stays the right call for now — it has zero
dependency on Cap CLI being installed at all (`ingest()` reads a `.cap`
directory's own files directly), which `cap export-preview` would not
replace, only complement. Worth revisiting once file-output frame export
ships: `export-preview`'s frames come out of Cap's own rendering pipeline
(zoom/crop/background applied), which PyAV's raw decode does not give you —
a real quality difference for the guide's screenshots, not just a
dependency question.
