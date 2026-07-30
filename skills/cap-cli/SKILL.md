---
name: cap-cli
description: Provides the `cap` command for Cap screen recording (CapSoftware/Cap) from WSL/Linux. Auto-detects cap-cli.exe and defines a shell function. Agents can verify with agent.sh.
user-invocable: true
allowed-tools: Bash(source ~/projects/cap-cli-skill/skills/cap-cli/setup.sh), Bash(source ~/projects/cap-cli-skill/skills/cap-cli/agent.sh), Bash(cap *)
---

# Cap CLI Skill

Provides the `cap` command for Cap screen recording from WSL/Linux by wrapping the Windows `cap-cli.exe`.

## Installation

```bash
# One-time load in current shell
source ~/projects/cap-cli-skill/skills/cap-cli/setup.sh

# Use cap commands
cap --version
cap doctor --json
cap targets --json
```

## For AI Agents (Pi, etc.)

Agents should run the verification script first:

```bash
source ~/projects/cap-cli-skill/agent.sh
cap doctor --json
cap targets --json
```

## Commands

| Command | Description |
|---------|-------------|
| `cap doctor --json` | Environment & capture readiness diagnostics |
| `cap targets --json` | List screens, windows, cameras, mics |
| `cap record start --screen <id> --detach --json` | Start background recording |
| `cap record stop --id <recordingId> --json` | Stop recording |
| `cap export <path.cap> --output out.mp4 --json` | Export to MP4 |
| `cap upload out.mp4 --json` | Upload to Cap (needs CAP_API_KEY) |
| `cap guide --json` | Agent capability manifest (Cap's own, not doc/SOP generation — see note below) |
| `cap auth status --json` | Check auth status |

This is a working subset for the record/export/upload flow this repo automates, not
the full surface. Cap's CLI has grown a much larger command set (`caps`, `organizations`,
`library`, `notifications`, `analytics`, `developers`, `jobs`, `automations`, `mcp serve`,
`agents install`, …) — run `cap guide --json` or `cap --help` for the authoritative,
current list.

## Relationship to Cap's own agent integration (as of 2026-07-18)

Cap now ships its **own** official agent integration — this predates our proposal work but
postdates this skill's creation (2026-06-08):

```bash
cap agents install --target claude --component all --dry-run --json   # preview
cap agents install --target claude --component all --yes --json       # apply
```

This installs Cap's bundled `SKILL.md` (routing rules, confirm-before-mutation policy, MCP
fallback logic — richer than this file) to `~/.claude/skills/cap/SKILL.md` and wires up
`cap mcp serve` in `~/.claude.json`, for Codex/Claude/Cursor. It's documented publicly at
`cap.so/docs/agents`.

**What that makes redundant:** the "teach an agent the `cap` command surface" job this
`SKILL.md` does by hand. Once `cap` resolves (see below), prefer `cap agents install` over
hand-maintaining this file's command table.

**What this skill still uniquely does:** make the `cap` command *resolve at all* from WSL.
Cap's installer now ships native Linux x86_64/aarch64 builds
(`curl -fsSL https://cap.so/install-cli.sh | sh`), but that doesn't help here — screen
capture has to happen against the Windows desktop, so bridging to the Windows-side
`cap-cli.exe` (what `setup.sh`/`agent.sh` do) remains necessary in this WSL topology even
though a native Linux `cap-cli` now exists for other setups.

Recommended order in this environment: `source setup.sh` (bridge `cap` to the Windows
binary) → `cap agents install --target claude --component all` (adopt Cap's own skill/MCP
instead of this one going forward).

## Configuration

```bash
export CAP_CLI_PATH="/custom/path/cap-cli.exe"  # Override binary location
export CAP_API_KEY="your-cap-auth-key"          # From Cap Settings
export CAP_SERVER_URL="https://cap.so"          # Or self-hosted URL
```

## Files

| File | Purpose |
|------|---------|
| `setup.sh` | Defines `cap()` shell function |
| `agent.sh` | Verification for agents |
| `SKILL.md` | This manifest |

## Requirements

- Cap Desktop installed on Windows (includes `cap-cli.exe`)
- WSL interop enabled
