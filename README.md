# Cap CLI Skill for Pi

A Pi Coding Agent skill that provides the `cap` command for Cap screen recording (CapSoftware/Cap) from WSL/Linux.

## Quick Start

```bash
# One-time load
source ~/projects/cap-cli-skill/setup.sh

# Install permanently to ~/.bashrc or ~/.zshrc
source ~/projects/cap-cli-skill/setup.sh --install

# Verify it works
cap --version
# cap 0.1.0
```

## Commands

| Command | Description |
|---------|-------------|
| `cap doctor --json` | Environment & capture readiness diagnostics |
| `cap targets --json` | List screens, windows, cameras, mics |
| `cap record start --screen <id> --detach --json` | Start background recording |
| `cap record stop --id <recordingId> --json` | Stop recording |
| `cap export <path.cap> --output out.mp4 --json` | Export to MP4 |
| `cap upload out.mp4 --json` | Upload to Cap (needs auth) |
| `cap guide --json` | Agent capability manifest |
| `cap auth status --json` | Check auth status |

## Agent Helper

```bash
# Check status
~/projects/cap-cli-skill/agent.sh status

# Verify installation (run in your shell)
source ~/projects/cap-cli-skill/agent.sh verify

# Run diagnostics
source ~/projects/cap-cli-skill/agent.sh doctor

# Re-setup
source ~/projects/cap-cli-skill/agent.sh setup
```

## Configuration

Environment variables (optional):
```bash
export CAP_API_KEY="your-cap-auth-key"      # From Cap Settings → API Keys
export CAP_SERVER_URL="https://cap.so"      # Or self-hosted URL
export CAP_WIN_USER="kyleb"                 # Windows username (if different)
export CAP_CLI_PATH="/custom/path/cap-cli.exe"  # Override binary location
```

## How It Works

- Detects Cap Desktop installation at `%LOCALAPPDATA%\Cap\cap-cli.exe`
- Creates a shell function `cap()` that wraps the Windows executable
- Works in bash, zsh, and fish
- `--install` flag adds `source ~/projects/cap-cli-skill/setup.sh` to shell config
- Idempotent: safe to run multiple times

## Files

| File | Purpose |
|------|---------|
| `setup.sh` | Main installer, defines `cap` function |
| `agent.sh` | Agent helper for setup/verify/status/doctor |
| `SKILL.md` | Pi skill manifest |

## Requirements

- Cap Desktop installed on Windows (v0.4.82+ includes CLI)
- WSL with interop enabled (default)

## License

MIT