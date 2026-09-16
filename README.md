# cap-tools

[![tests](https://github.com/kylebrodeur/cap-tools/actions/workflows/tests.yml/badge.svg)](https://github.com/kylebrodeur/cap-tools/actions/workflows/tests.yml)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows%20(WSL)-lightgrey.svg)

Automation and tooling for [Cap](https://cap.so) (CapSoftware/Cap) screen
recordings: drive a recording end to end from an agent or script (with
automatic zoom, no Studio required), and turn a finished recording into an
illustrated step-by-step guide.

Two complementary halves, one `capt` CLI:

| | **Record** | **Guide** |
|---|---|---|
| **What** | Automate a screen recording, with auto-zoom built from real click/keystroke markers | Turn a recording into an illustrated HTML/Markdown guide |
| **When** | Before you have a recording | After you have one |
| **Platforms** | macOS/Linux (native), WSL (bridges to Windows) | Any platform |
| **Docs** | [`docs/superpowers/specs/`](docs/superpowers/specs/) | [`guide/README.md`](guide/README.md) |

## Quick Start

```bash
cd ~/workspace/__Tools/cap-tools
uv sync
uv run capt --version
uv run capt --help
```

Use `uv run …` from this checkout; you do not need to activate `.venv`.
Launch Cap Desktop before preflight or recording:

```bash
open -a Cap
```

If the repository was moved and `uv` warns that `.venv` still points at
another checkout, recreate it once:

```bash
rm -rf .venv
uv sync
```

Do not use `uv sync --active` to silence a mismatch: that deliberately
targets whichever unrelated environment is already active.

```bash
uv run capt preflight --marker-source steps+global-capture
uv run capt record https://example.com --out recordings --screen <id> \
  --marker-source steps+global-capture --export-to demo.mp4 --json
uv run capt guide path/to/recording.cap --format both
```

`--screen <id>` records the full display; pass `--window <id>` instead (both
from `cap targets --json`) to capture just one window — the two are
mutually exclusive. `--pick` opens an interactive screen/window picker when
you're in a terminal (agents should always pass `--screen`/`--window`
explicitly). Every recording writes an events sidecar next to the `.cap`
(`<name>.events.json`) — the exact click/mark timeline, reusable by
`capt zoom apply` or any downstream tool.

For scripted recording against a logged-in app, authenticate the driven
browser with `--storage-state <playwright-state.json>` (cookies +
localStorage) or `--user-data-dir <profile-dir>` (full persistent profile —
IndexedDB/service workers/PWA state; wins when both are given).

Each `capt preflight` includes a `cap doctor` capture-readiness gate (G8).
Cap Desktop must be open; if it is closed, launch it with `open -a Cap`
and rerun preflight. G8 also catches a stale ScreenCaptureKit session
before it wastes a take.

For a live, narrated walkthrough (macOS only — no fixed length, no
`--steps`), `capt demo` is a shortcut that auto-detects the screen and
microphone and keeps recording until you press **Ctrl-C in the same
terminal**. `capt` catches that interrupt as a graceful stop request,
invokes `cap record stop` for the exact detached session, then finishes
the events sidecar, zoom merge, validation, and MP4 export:

```bash
uv run capt demo my-walkthrough --pick          # choose a live window/screen
uv run capt demo my-walkthrough                 # screen + mic auto-detected
uv run capt demo my-walkthrough --window <id>   # one window instead of the full screen
uv run capt demo my-walkthrough --no-mic        # skip narration audio
```

That's shorthand for `capt record --marker-source global-capture
--until-stopped`, with `--mic "<device>"` / `--system-audio` / `--camera <id>`
also available directly on `capt record` (device names/ids from
`cap targets --json`) if you want more control than `capt demo` gives you.

To record into another project without installing `capt` there, point
`uv` at cap-tools and give `capt` an explicit output directory. For
ReelBinder from the Slate checkout:

```bash
cd ~/workspace/slate
open -a Cap
uv run --project ~/workspace/__Tools/cap-tools \
  capt demo reelbinder-demo --pick \
  --out ~/workspace/slate/recordings
```

Choose the window whose owner is `ReelBinder`. When the walkthrough is
finished, return to this terminal and press **Ctrl-C once**. `capt` stops
the exact detached recording it started and safely completes validation,
the `.events.json` sidecar, zoom processing, and MP4 export.

`capt record` runs in-process on macOS/Linux — no browser-automation hop
required. On WSL it bridges to a Windows-hosted Cap Desktop install, since
screen capture has to target the Windows desktop (see
[`skills/cap-cli`](skills/cap-cli/) and `source skills/cap-cli/setup.sh`).

Full command reference: `capt <command> --help` for any of `record`, `guide`,
`export`, `assemble`, `preflight`, `config`, `zoom`, `scene`, `section`.

**New in Cap 0.6:** `capt scene` and `capt record/demo --scene` build
`timeline.camera3dSegments` — the camera orbits, tilts, or pushes around
the whole recording (see [`skills/capt-3d-scenes`](skills/capt-3d-scenes/)).
Verified headless on 0.6.0: an applied orbit scene renders through plain
`cap export` with no Studio. `capt config --preset gradient|animated` also
gains 0.6's moving gradient backgrounds.

**Verified beats & sections:** `capt record --steps` now fails loudly when a
scripted beat breaks (no more silent half-working takes) and writes a
`<name>.beats.json` completeness report. `capt section list/cut` turns a
beats report — or any events sidecar / hand-written sections JSON — into
labeled MP4 sections cut from the styled full-take export: record the whole
product take once, apply effects to it, export once, then cut sections for
the demo timeline without re-rendering.

## Install a skill into any agent

Skills under `skills/` follow the open [agentskills.io](https://agentskills.io)
spec — portable across Claude Code, Cursor, Codex, and any other
skills-compatible agent. Install one with a single `npx` call, no local clone
required:

```bash
npx github:kylebrodeur/cap-tools --list                              # see what's available
npx github:kylebrodeur/cap-tools cap-cli --target claude --dry-run   # preview
npx github:kylebrodeur/cap-tools cap-cli --target claude             # apply
npx github:kylebrodeur/cap-tools --all --target cursor               # install every skill found
```

`--target` is one of `codex`, `claude`, `cursor` — the same targets and path
convention as Cap's own `cap agents install`. See `bin/install-skill.js`.

## Structure

```
├── capt/                             # the capt CLI package
│   ├── cli.py                        # entry point: record/guide/export/assemble/preflight/config/zoom
│   ├── record/                       # shared beat-cycle core (beat.py, steps.py, macos_capture.py)
│   ├── guide/                        # ingest -> (transcribe) -> (structure) -> render pipeline
│   ├── zoom.py, config.py, export.py # zoom-segment building, project-config, cap export wrapper
│   └── preflight*.py                 # readiness gates, platform-dispatched
├── win/                              # Windows-side beat runner (invoked from WSL)
├── skills/cap-cli/                   # agentskills.io-compliant skill: bridges `cap` from WSL
├── bin/install-skill.js              # npx installer for skills/*
├── tests/                            # pytest suite (uv run pytest tests/)
├── docs/                             # design specs, plans, research, and reference material
│   └── superpowers/                  # brainstorming specs + implementation plans
├── guide/                            # earlier guide-pipeline prototype + working projects
└── upstream/                         # draft materials for a potential CapSoftware/Cap contribution
```

## Requirements

- **macOS/Linux:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Cap Desktop
  installed with its CLI on PATH (`curl -fsSL https://cap.so/install-cli.sh | sh`).
- **WSL:** the above, plus Cap Desktop installed on a Windows host and WSL
  interop enabled — screen capture always targets the Windows desktop.
- **Guide tool extras:** none required. Frame extraction prefers Cap's own
  `cap export-preview` when the CLI is available — it renders through
  Cap's native pipeline, so screenshots reflect the project's actual
  zoom/crop/background effects — and falls back automatically to vendored
  [PyAV](https://pyav.org/) (no system ffmpeg/ffprobe) when it isn't. A
  local OpenAI-compatible endpoint (e.g. Ollama) if using `--ai` step-text
  generation.
- **`capt assemble` only:** ffmpeg on PATH (multi-clip stitching with
  voiceover/captions still shells out to it).

Run the test suite with `uv run pytest tests/`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
