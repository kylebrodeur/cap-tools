#!/usr/bin/env bash
# SOURCE: an internal reference project/the source project/scripts/export-beat.sh
# ROLE: Reference implementation — export a .cap project to MP4.
# Wraps `cap export` with opinionated defaults (resolution, fps, quality).
#
# PROJECT-SPECIFIC: default resolution 1707x1067 (recording screen size).
# GENERIC: cap export invocation pattern, setup.sh source.
#
# Export a Cap Studio .cap project to an MP4 ready for assembly.
#
# Usage:
#   ./scripts/export-beat.sh path/to/beat.cap beat.mp4
#
# Defaults match the live Space recording settings (1707x1067, 60fps, maximum quality).

set -euo pipefail

SOURCE="${1:?Usage: $0 <project.cap> <output.mp4>}"
DEST="${2:?Usage: $0 <project.cap> <output.mp4>}"

source ~/projects/cap-cli-skill/setup.sh 2>/dev/null || true

echo "Exporting $(basename "$SOURCE") -> $(basename "$DEST")..."
cap export "$SOURCE" "$DEST" \
  --resolution 1707x1067 \
  --fps 60 \
  --quality maximum \
  --format mp4

echo "✓ Exported $DEST"
