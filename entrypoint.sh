#!/bin/sh
set -euo pipefail

# Base directory and config file
BASE_DIR="${BASE_DIR:-/app}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/config/config.json}"

# Ensure Python output is unbuffered
export PYTHONUNBUFFERED=1

# Use system Python (packages copied from builder)
PYTHON_BIN="/usr/local/bin/python"

echo "[INFO] Running initial metadata sync (watchdog disabled)..."
"$PYTHON_BIN" -u "$BASE_DIR/tubesync-plex-metadata.py" \
  --config "$CONFIG_FILE" --disable-watchdog

echo "[INFO] Starting folder watch according to config..."
exec "$PYTHON_BIN" -u "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE"
