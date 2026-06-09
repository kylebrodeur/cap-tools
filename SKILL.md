# Cap CLI Skill

Provides the `cap` command for Cap screen recording from WSL/Linux.

## Installation

This skill auto-configures a `cap` shell function that wraps the Windows `cap-cli.exe`.

## Usage

After loading the skill, `cap` is available as a native command:

```bash
cap doctor --json
cap targets --json
cap record start --screen <id> --detach --json
cap record stop --id <recordingId> --json
cap export <path.cap> --output out.mp4 --json
cap upload out.mp4 --json
```

## Configuration

Set these environment variables for headless/CI use:

```bash
export CAP_API_KEY="your-cap-auth-key"     # From Cap Settings
export CAP_SERVER_URL="https://cap.so"      # Or your self-hosted URL
```

## Auto-detection

The skill detects Cap installation at:
- Windows: `%LOCALAPPDATA%\Cap\cap-cli.exe`
- WSL path: `/mnt/c/Users/$USER/AppData/Local/Cap/cap-cli.exe`

Override with `CAP_CLI_PATH` if installed elsewhere.