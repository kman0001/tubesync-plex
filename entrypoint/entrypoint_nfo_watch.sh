#!/bin/bash
set -e

echo "[INFO] Processing existing NFO files in $WATCH_DIR..."
# 1회 실행: 기존 NFO 처리
/app/venv/bin/python /app/tubesync-plex-metadata.py --config "$CONFIG_FILE"

echo "[INFO] Starting NFO watch on $WATCH_DIR (recursive)..."
# 백그라운드 감시
exec inotifywait -m -r -e create --format "%f" "$WATCH_DIR" | while read FILE; do
    case "$FILE" in
        *.nfo)
            echo "[INFO] Detected NFO: $FILE"
            /app/venv/bin/python /app/tubesync-plex-metadata.py --config "$CONFIG_FILE"
            ;;
    esac
done
