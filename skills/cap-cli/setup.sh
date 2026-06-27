#!/usr/bin/env bash
# cap-cli skill setup - defines `cap` function for WSL/Linux
# Usage: source ~/projects/cap-cli-skill/setup.sh

CAP_CLI_PATH="${CAP_CLI_PATH:-/mnt/c/Users/<your-windows-username>/AppData/Local/Cap/cap-cli.exe}"

if [[ -f "$CAP_CLI_PATH" ]]; then
  cap() { "$CAP_CLI_PATH" "$@"; }
  echo "✓ cap -> $CAP_CLI_PATH"
else
  echo "⚠ cap-cli not found at $CAP_CLI_PATH" >&2
  return 1
fi
