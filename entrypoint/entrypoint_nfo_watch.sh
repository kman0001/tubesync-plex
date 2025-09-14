#!/bin/sh
set -e

WATCH_DIR=""
BASE_DIR=""

# 인자 처리
while [ "$#" -gt 0 ]; do
    case $1 in
        --watch-dir) WATCH_DIR="$2"; shift 2 ;;
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

[ -z "$WATCH_DIR" ] && echo "ERROR: --watch-dir must be specified" && exit 1
[ -z "$BASE_DIR" ] && echo "ERROR: --base-dir must be specified" && exit 1

CONFIG_FILE="$BASE_DIR/config/config.json"
PYTHON_BIN="$BASE_DIR/venv/bin/python"
PLEX_SCRIPT="$BASE_DIR/tubesync-plex-metadata.py"

# 새 NFO 감시
inotifywait -m -e create --format "%f" "$WATCH_DIR" | while read FILE; do
    case "$FILE" in
        *.nfo)
            echo "[INFO] Detected new NFO: $FILE"
            "$PYTHON_BIN" "$PLEX_SCRIPT" --config "$CONFIG_FILE" "$WATCH_DIR/$FILE"
            ;;
    esac
done
