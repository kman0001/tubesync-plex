#!/bin/sh
set -e

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# 환경변수 확인
: "${BASE_DIR:?BASE_DIR not set}"
: "${WATCH_DIR:?WATCH_DIR not set}"
: "${CONFIG_FILE:?CONFIG_FILE not set}"

PYTHON_BIN="$BASE_DIR/venv/bin/python"
PLEX_SCRIPT="$BASE_DIR/tubesync-plex-metadata.py"

log "Ensuring Python dependencies are installed..."
"$PYTHON_BIN" -m pip install --upgrade pip
REQ_FILE="$BASE_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    "$PYTHON_BIN" -m pip install --upgrade -r "$REQ_FILE"
fi

# ----------------------------
# 1. 기존 NFO 처리 (한번만)
# ----------------------------
log "Processing existing NFO files in $WATCH_DIR..."
"$PYTHON_BIN" "$PLEX_SCRIPT" --config "$CONFIG_FILE" --process-existing

# ----------------------------
# 2. 실시간 NFO 감시 시작
# ----------------------------
log "Starting recursive NFO watch on $WATCH_DIR..."
exec /bin/sh "$BASE_DIR/entrypoint_nfo_watch.sh" \
    --base-dir "$BASE_DIR" \
    --watch-dir "$WATCH_DIR" \
    --config "$CONFIG_FILE"
