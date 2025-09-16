#!/bin/sh
set -euo pipefail

BASE_DIR="${BASE_DIR:-/app}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/config/config.json}"

echo "[INFO] Running initial metadata sync (watchdog disabled)..."
/app/venv/bin/python -u "$BASE_DIR/tubesync-plex-metadata.py" \
  --config "$CONFIG_FILE" --disable-watchdog

echo "[INFO] Starting folder watch according to config..."
exec /app/venv/bin/python -u "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE"
