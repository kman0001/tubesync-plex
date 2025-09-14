#!/bin/sh
set -e

WATCH_DIR="/downloads"
BASE_DIR="/app"
CONFIG_FILE="/app/config/config.json"

log() { echo "[INFO] $1"; }

# ----------------------------
# 1. 기존 NFO 처리
# ----------------------------
for file in "$WATCH_DIR"/*.nfo; do
    [ -f "$file" ] && log "Processing existing NFO: $file" && \
    "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE" "$file"
done

# ----------------------------
# 2. NFO 감시 시작 (백그라운드)
# ----------------------------
log "Starting NFO watch on $WATCH_DIR..."
"$BASE_DIR/entrypoint/entrypoint_nfo_watch.sh" --base-dir "$BASE_DIR" --watch-dir "$WATCH_DIR" &
log "NFO watch running in background."

# ----------------------------
# 3. Main Tubesync process 실행
# ----------------------------
exec "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE"
