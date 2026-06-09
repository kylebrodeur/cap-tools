#!/usr/bin/env bash
# cap-cli skill setup - auto-configures `cap` command for WSL/Linux
# Usage: source setup.sh [--install]

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse args
INSTALL=false
for arg in "$@"; do
  case "$arg" in
    --install) INSTALL=true ;;
  esac
done

# Detect cap-cli.exe location
# WSL $USER may differ from Windows username; try both
WIN_USER="${CAP_WIN_USER:-kyleb}"
CAP_CLI_PATH="${CAP_CLI_PATH:-/mnt/c/Users/$WIN_USER/AppData/Local/Cap/cap-cli.exe}"

if [[ ! -f "$CAP_CLI_PATH" ]]; then
  # Try common alternative locations
  for alt in \
    "/mnt/c/Users/$WIN_USER/.cap/bin/cap.exe" \
    "/mnt/c/Program Files/Cap/cap-cli.exe" \
    "/usr/local/bin/cap-cli"; do
    if [[ -f "$alt" ]]; then
      CAP_CLI_PATH="$alt"
      break
    fi
  done
fi

if [[ ! -f "$CAP_CLI_PATH" ]]; then
  echo -e "${YELLOW}⚠ cap-cli not found at $CAP_CLI_PATH${NC}" >&2
  echo "  Set CAP_CLI_PATH or CAP_WIN_USER, or install Cap Desktop" >&2
  exit 1
fi

# Define the cap function
cap() {
  "$CAP_CLI_PATH" "$@"
}
# export -f works in bash; in zsh use autoload + typeset -fx or just define
if [[ -n "${ZSH_VERSION:-}" ]]; then
  # zsh: functions are automatically available
  typeset -fx cap 2>/dev/null || true
else
  # bash
  export -f cap
fi

echo -e "${GREEN}✓ cap-cli skill loaded: cap -> $CAP_CLI_PATH${NC}"

# --install: add to shell config
if [[ "$INSTALL" == true ]]; then
  # Detect shell config file
  SHELL_NAME="$(basename "$SHELL")"
  case "$SHELL_NAME" in
    bash)  CONFIG="$HOME/.bashrc" ;;
    zsh)   CONFIG="$HOME/.zshrc" ;;
    fish)  CONFIG="$HOME/.config/fish/config.fish" ;;
    *)     CONFIG="$HOME/.profile" ;;
  esac

  MARKER="# cap-cli skill (auto-added)"
  SOURCE_LINE="source $(realpath "${BASH_SOURCE[0]}")"

  if grep -q "$MARKER" "$CONFIG" 2>/dev/null; then
    echo -e "${BLUE}ℹ Already installed in $CONFIG${NC}"
  else
    echo "" >> "$CONFIG"
    echo "$MARKER" >> "$CONFIG"
    echo "$SOURCE_LINE" >> "$CONFIG"
    echo -e "${GREEN}✓ Added to $CONFIG — restart shell or run: source $CONFIG${NC}"
  fi
fi