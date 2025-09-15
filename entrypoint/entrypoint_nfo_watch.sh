#!/bin/bash
set -euo pipefail

# ================================
# 환경 변수 및 기본값
# ================================
BASE_DIR="${BASE_DIR:-/app}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/config/config.json}"
WATCH_DIRS="${WATCH_DIR:-/your/plex/library}"  # 쉼표로 구분 가능
DEBOUNCE_DELAY="${DEBOUNCE_DELAY:-2}"          # 마지막 이벤트 후 실행 대기 시간(초)

TIMER_PID=""

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
        "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE"
    ) 200>/tmp/tubesync-plex.lock
}

# ================================
# WATCH_DIRS → 배열 변환 (쉼표 구분)
# ================================
WATCH_DIR_LIST=()
IFS=',' read -ra DIR_ARRAY <<< "$WATCH_DIRS"
for DIR in "${DIR_ARRAY[@]}"; do
    DIR=$(echo "$DIR" | xargs)  # 공백 제거
    if [[ -d "$DIR" ]]; then
        WATCH_DIR_LIST+=("$DIR")
    else
        echo "[WARNING] Directory does not exist: $DIR"
    fi
done

# ================================
# 감시할 디렉터리 없는 경우 대기
# ================================
if [[ ${#WATCH_DIR_LIST[@]} -eq 0 ]]; then
    echo "[INFO] No valid directories to watch. Container will wait..."
    while true; do sleep 60; done
fi

# ================================
# 1회 실행: 기존 NFO 처리
# ================================
echo "[INFO] Processing existing NFO files in all watch directories..."
run_job

# ================================
# inotify 감시 시작
# ================================
echo "[INFO] Starting NFO watch on directories: ${WATCH_DIR_LIST[*]}"
exec inotifywait -m -r \
  -e close_write,create,moved_to \
  --format "%w%f" "${WATCH_DIR_LIST[@]}" | while read -r FILE; do
    case "$FILE" in
        *.nfo)
            echo "[INFO] Detected NFO: $FILE"

            # 기존 타이머 취소 → de-bounce
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
