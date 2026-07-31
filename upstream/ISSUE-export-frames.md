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
Same context as our earlier `cap doc` proposal (see the other issue in this
batch) — Cap's CLI surface is clearly meant to be the foundation other tools
build on (`cap agents install`, the MCP server, the whole "designed to be
driven by automation and AI agents" framing in `cap --help`). Every one of
those downstream tools that wants a still frame currently has to solve the
exact fragility we just hit, independently, on their own.

### Status
No PR yet — wanted to check appetite and naming/shape preference first,
same as our other proposal. Happy to prototype against `crates/export` if
this is a direction you'd take a contribution on.
