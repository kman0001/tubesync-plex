#!/bin/bash
set -e

BASE_DIR=""
WATCH_DIR="/downloads"

while [ "$#" -gt 0 ]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --watch-dir) WATCH_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$BASE_DIR" ]; then
    echo "ERROR: --base-dir must be specified"
    exit 1
fi

PYTHON_BIN="$BASE_DIR/venv/bin/python"
PLEX_SCRIPT="$BASE_DIR/tubesync-plex-metadata.py"
CONFIG_FILE="$BASE_DIR/config.json"

# Start NFO watch
echo "[INFO] Starting NFO watch on $WATCH_DIR..."
(
    inotifywait -m -e create --format "%f" "$WATCH_DIR" | while read FILE; do
        [[ "$FILE" == *.nfo ]] && echo "[INFO] Detected $FILE, running Plex sync..." && \
        "$PYTHON_BIN" "$PLEX_SCRIPT" --config "$CONFIG_FILE"
    done
) &

echo "[INFO] NFO watch running in background."

# Execute additional commands if any
exec "$@"
