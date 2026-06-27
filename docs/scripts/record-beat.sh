#!/usr/bin/env bash
# SOURCE: an internal reference project/the source project/scripts/record-beat.sh
# ROLE: Reference implementation — per-beat recording orchestrator.
# Start Cap, drive one named UI segment via Playwright CDP, stop Cap.
# One .cap project per beat, clean in/out points.
#
# PROJECT-SPECIFIC: SPACE URL, beat names, Chrome binary path.
# GENERIC: Cap detach pattern, CDP check, screen ID discovery.
#
# Record a single demo beat to its own .cap project.
# Reuses the same Chrome CDP window; starts/stops Cap per beat so each beat
# becomes a clean, short clip in Cap Studio.
#
# Usage from WSL inside the source project/:
#   ./record-beat.sh load
#   ./record-beat.sh slice
#   ./record-beat.sh second
#   ./record-beat.sh scrub
#   ./record-beat.sh placement
#   ./record-beat.sh climb
#   ./record-beat.sh print
#   ./record-beat.sh review
#
# Requirements: Chrome + Cap + pnpm Playwright already set up (run ./record-studio.sh once).

set -euo pipefail

cd "$(dirname "$0")"

source ~/projects/cap-cli-skill/setup.sh 2>/dev/null || true

HOST_IP=$(ip route show | grep default | awk '{print $3}')
export CDP_URL="http://${HOST_IP}:9222"
CHROME="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
SPACE="https://node.your-target-app.example.com/?__theme=dark"

# Launch Chrome if not already alive
if ! curl -s "${CDP_URL}/json/version" >/dev/null 2>&1; then
    echo "Launching Chrome app window..."
    PROFILE_DIR="/tmp/chrome-studio-profile-$(date +%s)"
    mkdir -p "$PROFILE_DIR"
    nohup "${CHROME}" --app="${SPACE}" --remote-debugging-port=9222 \
        --remote-debugging-address=0.0.0.0 \
        --user-data-dir="$PROFILE_DIR" \
        --window-size=1707,1067 \
        --window-position=0,0 \
        --disable-session-crashed-bubble --no-first-run \
        --no-default-browser-check --disable-features=TranslateUI \
        >/tmp/chrome-beat.log 2>&1 &
    sleep 5
else
    echo "Chrome CDP already alive — reusing existing window"
fi

BEAT="${1:-all}"
shift || true

# Map beat names to the driver beat argument
BEAT_ARG="${BEAT}"
case "$BEAT" in
  load)      BEAT_ARG="load" ;;
  slice)     BEAT_ARG="slice" ;;
  second)    BEAT_ARG="second" ;;
  scrub)     BEAT_ARG="scrub" ;;
  placement) BEAT_ARG="placement" ;;
  climb)     BEAT_ARG="climb" ;;
  print)     BEAT_ARG="loop" ;;
  review)    BEAT_ARG="loop" ;;
esac

SCREEN_ID=$(cap targets screens --json | python3 -c 'import sys,json; d=json.load(sys.stdin); print([s for s in d if s.get("primary")][0]["id"])')
echo "Recording beat: ${BEAT}  (driver=${BEAT_ARG})  (screen=${SCREEN_ID})"

CAP_START_TMP="/tmp/cap-beat-start-$(date +%s).txt"
echo "Starting Cap recording..."
rm -f "$CAP_START_TMP"
nohup /mnt/c/Users/<your-windows-username>/AppData/Local/Cap/cap-cli.exe record start --screen "$SCREEN_ID" --fps 60 --detach --json > "$CAP_START_TMP" 2>&1 &
CAP_PID=$!
sleep 3

# Parse the JSON Cap emitted
REC_ID=""
if [[ -s "$CAP_START_TMP" ]]; then
    REC_ID=$(python3 -c "import sys,json; data=open(sys.argv[1]).read(); print([json.loads(l) for l in data.splitlines() if l.strip().startswith('{') and l.strip().endswith('}')][0]['recordingId'])" "$CAP_START_TMP")
fi

if [[ -z "$REC_ID" ]]; then
    echo "  ✗ could not parse Cap recording ID; output was:"
    cat "$CAP_START_TMP" || true
    wait "$CAP_PID" 2>/dev/null || true
    exit 1
fi

echo "  ✓ Cap recording started (${REC_ID})"

echo "Driving beat..."
node scripts/record-studio.cjs --skip-cap --beat="${BEAT_ARG}" "$@" || true

echo "Stopping Cap recording..."
cap record stop --id "${REC_ID}" || true
echo "  ✓ Beat ${BEAT} done — raw .cap project ready in Cap Studio"
