#!/usr/bin/env bash
# cap-cli agent verification - verifies cap function works
# Usage: source ~/projects/cap-cli-skill/agent.sh

CAP_CLI_PATH="${CAP_CLI_PATH:-/mnt/c/Users/<your-windows-username>/AppData/Local/Cap/cap-cli.exe}"

if [[ -f "$CAP_CLI_PATH" ]]; then
  cap() { "$CAP_CLI_PATH" "$@"; }
  version=$(cap --version 2>/dev/null | head -1)
  echo "✓ cap-cli found: $CAP_CLI_PATH"
  echo "✓ cap works: $version"
  echo "→ Cap now ships its own agent skill/MCP installer: 'cap agents install --target claude --component all --dry-run --json'"
  exit 0
else
  echo "✗ cap-cli not found at $CAP_CLI_PATH"
  exit 1
fi
