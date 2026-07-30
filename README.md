# cap-tools

Tools for working with Cap screen recordings (CapSoftware/Cap) from WSL.

Two complementary halves:

| | **Record** | **Guide** |
|---|---|---|
| **What** | Automate browser-driven recordings | Turn recordings into illustrated step-by-step docs |
| **When** | Before the recording | After the recording |
| **Status** | Design phase | Validated prototype |
| **Docs** | [`docs/architecture.md`](docs/ARCHITECTURE.md) | [`guide/README.md`](guide/README.md) |

## Quick Start — Cap CLI

```bash
source skills/cap-cli/setup.sh
cap --version
cap doctor --json
cap targets --json
```

## Quick Start — Install skills into any agent

Skills under `skills/` follow the open [agentskills.io](https://agentskills.io) spec —
portable across Claude Code, Cursor, Codex, and any other skills-compatible agent.
Install one with a single `npx` call, no local clone required:

```bash
npx github:kylebrodeur/cap-tools --list                              # see what's available
npx github:kylebrodeur/cap-tools cap-cli --target claude --dry-run   # preview
npx github:kylebrodeur/cap-tools cap-cli --target claude             # apply
npx github:kylebrodeur/cap-tools --all --target cursor               # install every skill found
```

`--target` is one of `codex`, `claude`, `cursor` (same targets and path convention as
Cap's own `cap agents install`). See `bin/install-skill.js`.

## Quick Start — Guide Tool

```bash
cd guide
uv sync
uv run spike/cap_ingest.py "C:/path/to/recording.cap"
```

## Structure

```
├── bin/install-skill.js             # npx installer — installs skills/* into codex/claude/cursor
├── package.json                     # names the npx entry point above
├── skills/cap-cli/                  # cap CLI shim for WSL (agentskills.io)
│   ├── SKILL.md, setup.sh, agent.sh
├── docs/                            # all documentation
│   ├── architecture.md              # Record half design
│   ├── findings.md                  # cross-project research
│   ├── project-config-schema.md     # .cap config reference
│   ├── decisions.md                 # Guide half decision log
│   ├── productization.md            # market + strategy
│   ├── upstream-proposal.md         # cap doc RFC (renamed from cap guide — see its Status update)
│   └── reference/                   # reference scripts
├── guide/                           # Guide half (working code)
│   ├── spike/                       # core pipeline (cap_ingest, structure, build_walkthrough_doc, transcribe)
│   ├── _archive/                    # superseded scripts (assemble, record, extract_frames)
│   ├── guide.py, mcp_server.py      # CLI + MCP
│   └── projects/                    # working projects
└── record/                          # Record half (to be built)
```

## Requirements

- Cap Desktop installed on Windows
- WSL interop enabled
- For guide tool: Python 3.11+, uv, ffmpeg on PATH
