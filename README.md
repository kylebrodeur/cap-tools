# cap-tools

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
uv sync
uv run capt --help
```

```bash
capt preflight --marker-source steps+global-capture   # check readiness
capt record https://example.com --out recordings --screen <id> \
  --marker-source steps+global-capture --export-to demo.mp4 --json
capt guide path/to/recording.cap --format both
```

`capt record` runs in-process on macOS/Linux — no browser-automation hop
required. On WSL it bridges to a Windows-hosted Cap Desktop install, since
screen capture has to target the Windows desktop (see
[`skills/cap-cli`](skills/cap-cli/) and `source skills/cap-cli/setup.sh`).

Full command reference: `capt <command> --help` for any of `record`, `guide`,
`export`, `assemble`, `preflight`, `config`, `zoom`.

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
- **Guide tool extras:** ffmpeg on PATH; a local OpenAI-compatible endpoint
  (e.g. Ollama) if using `--ai` step-text generation.

Run the test suite with `uv run pytest tests/`.

## License

[MIT](LICENSE)
