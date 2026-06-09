---
name: cap-cli
description: Provides the `cap` command for Cap screen recording (CapSoftware/Cap) from WSL/Linux. Auto-detects cap-cli.exe and defines a shell function. Agents can verify with agent.sh.
user-invocable: true
allowed-tools: Bash(source ~/projects/cap-cli-skill/setup.sh), Bash(source ~/projects/cap-cli-skill/agent.sh), Bash(cap *)
---

# Cap CLI Skill

Provides the `cap` command for Cap screen recording from WSL/Linux by wrapping the Windows `cap-cli.exe`.

## Installation

```bash
# One-time load in current shell
source ~/projects/cap-cli-skill/setup.sh

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
| `cap guide --json` | Agent capability manifest |
| `cap auth status --json` | Check auth status |

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
