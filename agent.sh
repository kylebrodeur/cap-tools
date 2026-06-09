#!/usr/bin/env bash
# cap-cli agent helper - for Pi agent to set up and verify cap-cli
# Usage: agent.sh {setup|verify|status|doctor}

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
SETUP_SCRIPT="$SKILL_DIR/setup.sh"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[cap-cli]${NC} $*"; }
ok() { echo -e "${GREEN}[cap-cli]${NC} $*"; }
warn() { echo -e "${YELLOW}[cap-cli]${NC} $*"; }
err() { echo -e "${RED}[cap-cli]${NC} $*" >&2; }

# Detect Windows username
detect_win_user() {
  local candidates=("kyleb" "$USER" "kylebrodeur")
  for u in "${candidates[@]}"; do
    if [[ -d "/mnt/c/Users/$u" ]]; then
      echo "$u"
      return 0
    fi
  done
  echo "kyleb"  # fallback
}

# Check if cap-cli.exe exists
find_cap_cli() {
  local win_user="${CAP_WIN_USER:-$(detect_win_user)}"
  local paths=(
    "/mnt/c/Users/$win_user/AppData/Local/Cap/cap-cli.exe"
    "/mnt/c/Users/$win_user/.cap/bin/cap.exe"
    "/mnt/c/Program Files/Cap/cap-cli.exe"
    "/usr/local/bin/cap-cli"
  )
  for p in "${paths[@]}"; do
    if [[ -f "$p" ]]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

# Check if skill is installed in shell config
is_installed() {
  local shell_name="$(basename "$SHELL")"
  local config
  case "$shell_name" in
    bash) config="$HOME/.bashrc" ;;
    zsh)  config="$HOME/.zshrc" ;;
    fish) config="$HOME/.config/fish/config.fish" ;;
    *)    config="$HOME/.profile" ;;
  esac
  grep -q "cap-cli skill (auto-added)" "$config" 2>/dev/null
}

# Verify cap command works
verify_cap() {
  # Check if cap is a function (bash/zsh) or command
  if declare -f cap >/dev/null 2>&1 || typeset -f cap >/dev/null 2>&1 || command -v cap >/dev/null 2>&1; then
    local version
    version=$(cap --version 2>/dev/null | head -1)
    ok "cap command available: $version"
    return 0
  else
    err "cap command not found (not a function, not in PATH)"
    return 1
  fi
}

cmd_setup() {
  log "Setting up cap-cli..."
  local cap_path
  if cap_path=$(find_cap_cli); then
    CAP_CLI_PATH="$cap_path" source "$SETUP_SCRIPT" --install
    ok "Setup complete"
  else
    err "cap-cli.exe not found. Install Cap Desktop first."
    err "Checked locations:"
    local win_user="${CAP_WIN_USER:-$(detect_win_user)}"
    for p in "/mnt/c/Users/$win_user/AppData/Local/Cap/cap-cli.exe" "/mnt/c/Users/$win_user/.cap/bin/cap.exe" "/mnt/c/Program Files/Cap/cap-cli.exe"; do
      err "  $p"
    done
    exit 1
  fi
}

cmd_verify() {
  log "Verifying cap-cli installation..."
  local cap_path
  if cap_path=$(find_cap_cli); then
    ok "Found cap-cli.exe at: $cap_path"
  else
    err "cap-cli.exe not found"
    exit 1
  fi

  if is_installed; then
    ok "Skill installed in shell config"
  else
    warn "Skill NOT installed in shell config (run 'setup')"
  fi

  if verify_cap; then
    ok "cap command works"
  else
    warn "cap command not available in current shell (restart or source config)"
  fi
}

cmd_status() {
  log "cap-cli status"
  echo "  Shell: $(basename "$SHELL")"
  echo "  Windows user: ${CAP_WIN_USER:-$(detect_win_user)}"
  
  if cap_path=$(find_cap_cli); then
    echo "  cap-cli.exe: $cap_path"
  else
    echo "  cap-cli.exe: NOT FOUND"
  fi
  
  if is_installed; then
    echo "  Shell config: INSTALLED"
  else
    echo "  Shell config: NOT INSTALLED"
  fi
  
  if command -v cap >/dev/null 2>&1; then
    echo "  cap command: AVAILABLE"
    cap --version 2>/dev/null | head -1 | sed 's/^/    /'
  else
    echo "  cap command: NOT AVAILABLE"
  fi
}

cmd_doctor() {
  log "Running cap-cli doctor..."
  if cap_path=$(find_cap_cli); then
    "$cap_path" doctor --json
  else
    err "cap-cli.exe not found"
    exit 1
  fi
}

# Main
case "${1:-help}" in
  setup)    cmd_setup ;;
  verify)   cmd_verify ;;
  status)   cmd_status ;;
  doctor)   cmd_doctor ;;
  *)        echo "Usage: $0 {setup|verify|status|doctor}" ;;
esac