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
source setup.sh
cap --version
cap doctor --json
cap targets --json
```

## Quick Start — Guide Tool

```bash
cd guide
uv sync
uv run spike/cap_ingest.py "C:/path/to/recording.cap"
```

## Structure

```
├── setup.sh, agent.sh, SKILL.md    # cap CLI shim for WSL
├── docs/                            # all documentation
│   ├── architecture.md              # Record half design
│   ├── findings.md                  # cross-project research
│   ├── project-config-schema.md     # .cap config reference
│   ├── decisions.md                 # Guide half decision log
│   ├── productization.md            # market + strategy
│   ├── upstream-proposal.md         # cap guide RFC
│   └── reference/                   # reference scripts
├── guide/                           # Guide half (working code)
│   ├── spike/                       # pipeline scripts
│   ├── guide.py, mcp_server.py      # CLI + MCP
│   └── projects/                    # working projects
└── record/                          # Record half (to be built)
```

## Requirements

- Cap Desktop installed on Windows
- WSL interop enabled
- For guide tool: Python 3.11+, uv, ffmpeg on PATH
