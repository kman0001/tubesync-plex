#!/bin/sh
set -euo pipefail

# Base directory and config file
BASE_DIR="${BASE_DIR:-/app}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/config/config.json}"

# Ensure Python output is unbuffered
export PYTHONUNBUFFERED=1

# Use venv Python
PYTHON_BIN="$BASE_DIR/venv/bin/python"

exec "$PYTHON_BIN" -u "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE" "$@"
