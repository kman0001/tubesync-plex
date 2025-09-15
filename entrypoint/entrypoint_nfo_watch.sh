#!/bin/bash
set -euo pipefail

# ================================
# 환경 변수 체크
# ================================
if [[ -z "${WATCH_DIR:-}" ]]; then
    echo "[ERROR] WATCH_DIR is not set"
    exit 1
fi

if [[ -z "${CONFIG_FILE:-}" ]]; then
    echo "[ERROR] CONFIG_FILE is not set"
    exit 1
fi

DEBOUNCE_DELAY=2  # 마지막 이벤트 후 실행 대기 시간(초)
TIMER_PID=""      # 현재 대기 중인 타이머 프로세스 ID

# ================================
# 실행 함수
# ================================
run_job() {
    (
        flock -n 200 || {
            echo "[INFO] Another process is already running, skipping..."
            exit 0
        }
        echo "[INFO] Running tubesync-plex-metadata.py..."
        /app/venv/bin/python /app/tubesync-plex-metadata.py --config "$CONFIG_FILE"
    ) 200>/tmp/tubesync-plex.lock
}

# ================================
# 1회 실행: 기존 NFO 처리
# ================================
echo "[INFO] Processing existing NFO files in $WATCH_DIR..."
run_job

# ================================
# inotify 감시 시작
# ================================
echo "[INFO] Starting NFO watch on $WATCH_DIR (recursive)..."

exec inotifywait -m -r \
  -e close_write,create,moved_to \
  --format "%w%f" "$WATCH_DIR" | while read -r FILE; do
    case "$FILE" in
        *.nfo)
            echo "[INFO] Detected NFO: $FILE"

            # 기존 타이머 취소 → 타이머 리셋
            if [[ -n "$TIMER_PID" ]] && kill -0 "$TIMER_PID" 2>/dev/null; then
                echo "[INFO] Resetting debounce timer..."
                kill "$TIMER_PID"
                wait "$TIMER_PID" 2>/dev/null || true
            fi

            # 새로운 타이머 시작
            (
                sleep "$DEBOUNCE_DELAY"
                run_job
            ) &
            TIMER_PID=$!
            ;;
    esac
done
