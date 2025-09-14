#!/bin/bash
set -e

BASE_DIR=""
WATCH_DIR=""

# 인수 파싱
while [ "$#" -gt 0 ]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --watch-dir) WATCH_DIR="$2"; shift 2 ;;
        *) echo "Unknown option $1"; exit 1 ;;
    esac
done

if [ -z "$BASE_DIR" ] || [ -z "$WATCH_DIR" ]; then
    echo "ERROR: --base-dir and --watch-dir must be specified"
    exit 1
fi

PYTHON_BIN="$BASE_DIR/venv/bin/python"
PLEX_SCRIPT="$BASE_DIR/tubesync-plex-metadata.py"
CONFIG_FILE="$BASE_DIR/config/config.json"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

log "Watching NFO files in $WATCH_DIR (recursive)..."

inotifywait -m -r -e create --format "%f %w" "$WATCH_DIR" | while read FILE DIR; do
    if [[ "$FILE" == *.nfo ]]; then
        log "Detected new NFO: $DIR$FILE"
        "$PYTHON_BIN" "$PLEX_SCRIPT" --config "$CONFIG_FILE" --file "$DIR$FILE"
    fi
done
