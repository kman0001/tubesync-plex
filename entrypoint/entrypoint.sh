#!/bin/bash
set -e

BASE_DIR="/app"
WATCH_DIR="/downloads"
CONFIG_FILE="/app/config/config.json"
PYTHON_BIN="$BASE_DIR/venv/bin/python"
PLEX_SCRIPT="$BASE_DIR/tubesync-plex-metadata.py"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

log "Processing existing NFO files..."
# 기존 NFO 1회 처리
"$PYTHON_BIN" "$PLEX_SCRIPT" --config "$CONFIG_FILE" --process-existing --watch-dir "$WATCH_DIR"

log "Starting NFO watch in background..."
# 백그라운드 감시
"$BASE_DIR/entrypoint_nfo_watch.sh" --base-dir "$BASE_DIR" --watch-dir "$WATCH_DIR" &

log "NFO watch running in background."

# 메인 프로세스 실행 (필요시)
exec "$BASE_DIR/main_tubesync_process.sh"
