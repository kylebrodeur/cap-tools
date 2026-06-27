# cap-cli-skill — docs

Research, findings, and design work toward a proper CLI extension for Cap screen recording.

## Contents

| File | What it is |
|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | **Start here for the build.** Design decisions, beat cycle, module breakdown, stack layout, build phases |
| [INVENTORY.md](./INVENTORY.md) | 118 numbered items across all projects — every unique technique, pattern, finding, sourced and tagged |
| [FINDINGS.md](./FINDINGS.md) | Narrative findings from cross-project research — CDP/WSL reliability, agent-browser bridge, Cap CLI JSON API, project-config schema |
| [PROJECT-CONFIG-SCHEMA.md](./PROJECT-CONFIG-SCHEMA.md) | Full annotated `project-config.json` schema — zoom, background, cursor, captions, keyboard overlays |
| [USE-CASES.md](./USE-CASES.md) | 13 generalized use cases for browser-driven recording workflows |
| [REFACTOR-PLAN.md](./REFACTOR-PLAN.md) | Earlier refactor plan (superseded by DESIGN.md for architecture; still useful for phase staging) |
| [MY-SETUP.md](./MY-SETUP.md) | Machine-specific reference — IPs, screen IDs, camera/mic names, tool paths |
| [scripts/README.md](./scripts/README.md) | Index of gathered reference scripts with source annotations |

## Context

This skill started as a thin WSL shim for `cap-cli.exe`. Research across
multiple projects revealed a richer surface and a clean architecture:

**The bridge:** `agent-browser --headed` (WSLg) launches Linux Chrome as a
visible Windows window. `cap record --window <id>` captures that window
specifically. The two tools are fully independent — no CDP cross-boundary,
no Windows Defender Firewall issue. Full design in [DESIGN.md](./DESIGN.md).

See [INVENTORY.md](./INVENTORY.md) for the complete list of 118 unique
techniques and patterns gathered from all source projects.
