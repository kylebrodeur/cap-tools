---
name: cap-cli
description: Bridges the `cap` command from a WSL/Linux session to a Windows-hosted Cap Desktop installation, since Cap screen capture must target the Windows desktop. Use when `cap` is not on PATH in WSL. Not needed on native macOS/Linux — Cap's own installer already places a native `cap` binary there.
compatibility: WSL topology only. Requires Cap Desktop installed on Windows and WSL interop enabled.
metadata:
  supersedes: none — narrower and complementary to Cap's own bundled skill (see below), not a replacement
---

# Cap CLI WSL Bridge

Cap ships its own comprehensive agent skill and MCP server (installed via
`cap agents install --target <agent> --component all`), covering the full
CLI/MCP surface, confirmation rules, and safety policy — see
`cap.so/docs/agents`. This skill's job is narrower and complementary: making
the `cap` command **resolve at all** from a WSL session. Screen capture has
to run against the Windows desktop, so `cap` here means the Windows-side
`cap-cli.exe`, not a WSL-native binary.

## When to use this

Only in a WSL topology, when `cap` is not already on PATH. On native
macOS/Linux, Cap's installer (`curl -fsSL https://cap.so/install-cli.sh | sh`)
already places a native `cap` binary there — this bridge does nothing useful
in that environment and should be skipped.

## Setup

Bridge `cap` to the Windows-side binary, then verify:

```bash
source skills/cap-cli/setup.sh
source skills/cap-cli/agent.sh
cap --version
```

Once `cap` resolves, install Cap's own skill/MCP for everything else — don't
hand-maintain a command table here when `cap guide --json` and
`cap agents install` already keep it current:

```bash
cap agents install --target claude --component all --dry-run --json   # preview
cap agents install --target claude --component all --yes --json       # apply
```

## Configuration

```bash
export CAP_CLI_PATH="/custom/path/cap-cli.exe"  # Override binary location
export CAP_API_KEY="your-cap-auth-key"          # From Cap Settings
export CAP_SERVER_URL="https://cap.so"          # Or self-hosted URL
```

## Files

| File | Purpose |
|------|---------|
| `setup.sh` | Defines the `cap()` shell function bridging to `cap-cli.exe` |
| `agent.sh` | Verifies the bridge works and points agents at `cap agents install` |
| `SKILL.md` | This file |
