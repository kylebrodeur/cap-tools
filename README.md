# Cap CLI Skill for Pi

Simple alias for Cap screen recording CLI from WSL/Linux.

## Usage

```bash
# Load in current shell
source ~/projects/cap-cli-skill/setup.sh

# Use cap command
cap --version
cap doctor --json
cap targets --json
```

## For AI Agents (Pi, etc.)

Agents can run the verification directly:
```bash
# Verify cap works
~/projects/cap-cli-skill/agent.sh

# Or source and use
source ~/projects/cap-cli-skill/setup.sh && cap doctor --json
```

## Configuration

```bash
export CAP_CLI_PATH="/custom/path/cap-cli.exe"  # Override binary location
```

## Files

| File | Purpose |
|------|---------|
| `setup.sh` | Defines `cap` alias |
| `agent.sh` | Verification for agents |
| `SKILL.md` | Pi skill manifest |

## Requirements

- Cap Desktop installed on Windows (includes `cap-cli.exe`)
- WSL interop enabled
