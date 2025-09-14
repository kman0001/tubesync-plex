#!/bin/sh
set -e

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

WATCH_DIR="/downloads"
BASE_DIR=""
CONFIG_FILE=""

while [ "$#" -gt 0 ]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --watch-dir) WATCH_DIR="$2"; shift 2 ;;
        --config) CONFIG_FILE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$BASE_DIR" ] || [ -z "$WATCH_DIR" ] || [ -z "$CONFIG_FILE" ]; then
    echo "ERROR: --base-dir, --watch-dir, and --config must be specified"
    exit 1
fi

PYTHON_BIN="$BASE_DIR/venv/bin/python"
PLEX_SCRIPT="$BASE_DIR/tubesync-plex-metadata.py"

# 재귀 감시
log "Setting up recursive NFO watch on $WATCH_DIR..."
inotifywait -m -r -e create --format "%f" "$WATCH_DIR" | while read FILE; do
    case "$FILE" in
        *.nfo)
            log "Detected new NFO: $FILE, running Plex metadata sync..."
            "$PYTHON_BIN" "$PLEX_SCRIPT" --config "$CONFIG_FILE"
            ;;
    esac
done
