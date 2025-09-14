#!/bin/sh
set -e

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# 기본 경로 설정
# ----------------------------
WATCH_DIR="${WATCH_DIR:-/downloads}"
BASE_DIR="${BASE_DIR:-/app}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/config/config.json}"
PYTHON_BIN="$BASE_DIR/venv/bin/python"
PLEX_SCRIPT="$BASE_DIR/tubesync-plex-metadata.py"

# ----------------------------
# 1회 실행: 기존 NFO 파일 처리
# ----------------------------
log "Processing existing NFO files in $WATCH_DIR..."
find "$WATCH_DIR" -type f -name "*.nfo" | while read f; do
    log "Processing existing NFO: $f"
    "$PYTHON_BIN" "$PLEX_SCRIPT" --config "$CONFIG_FILE" --file "$f"
done

# ----------------------------
# 백그라운드 감시 (재귀)
# ----------------------------
log "Starting NFO watch on $WATCH_DIR (recursive)..."
(
    inotifywait -m -r -e create -e moved_to -e modify --format "%w%f" "$WATCH_DIR" | while read FILE; do
        case "$FILE" in
            *.nfo)
                log "Detected NFO: $FILE, running Plex metadata sync..."
                "$PYTHON_BIN" "$PLEX_SCRIPT" --config "$CONFIG_FILE" --file "$FILE"
                ;;
        esac
    done
) &

log "NFO watch running in background."

# ----------------------------
# 컨테이너 주 프로세스 실행
# ----------------------------
exec "$@"
