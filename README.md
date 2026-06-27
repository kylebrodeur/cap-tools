# cap-cli-skill

Tools for working with Cap screen recordings (CapSoftware/Cap) from WSL.

Two complementary halves:

| | **Record** | **Guide** |
|---|---|---|
| **What** | Automate browser-driven recordings | Turn recordings into illustrated step-by-step docs |
| **When** | Before the recording | After the recording |
| **Docs** | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | [`guide/README.md`](guide/README.md) |
| **Status** | Design phase | Validated prototype |

## Quick Start — Cap CLI

```bash
source ~/projects/cap-cli-skill/setup.sh
cap --version
cap doctor --json
cap targets --json
```

## Quick Start — Guide Tool

```bash
cd guide
uv sync
uv run spike/cap_ingest.py "C:/path/to/recording.cap"
# → spike/spike-output/cap/<name>/guide.html
```

## Docs

| File | What |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Design decisions, beat cycle, module breakdown, build phases |
| [`docs/FINDINGS.md`](docs/FINDINGS.md) | 20 technical findings from cross-project research |
| [`docs/INVENTORY.md`](docs/INVENTORY.md) | 118 numbered items — every technique, pattern, finding |
| [`docs/PROJECT-CONFIG-SCHEMA.md`](docs/PROJECT-CONFIG-SCHEMA.md) | Full annotated `project-config.json` schema |
| [`docs/USE-CASES.md`](docs/USE-CASES.md) | 13 generalised use cases |
| [`docs/MY-SETUP.md`](docs/MY-SETUP.md) | Machine-specific reference |
| [`guide/CAP-UPSTREAM-PROPOSAL.md`](guide/CAP-UPSTREAM-PROPOSAL.md) | RFC: `cap guide` upstream to CapSoftware/Cap |
| [`guide/PRODUCTIZATION.md`](guide/PRODUCTIZATION.md) | Market landscape + productization strategy |
| [`guide/DECISIONS.md`](guide/DECISIONS.md) | Decision log D1–D10 |
| [`guide/ROADMAP.md`](guide/ROADMAP.md) | Current state + backlog |

## Requirements

- Cap Desktop installed on Windows (includes `cap-cli.exe`)
- WSL interop enabled
- For guide tool: Python 3.11+, uv, ffmpeg on PATH
