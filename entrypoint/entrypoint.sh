#!/bin/sh
set -e

BASE_DIR=${BASE_DIR:-/app}
WATCH_DIR=${WATCH_DIR:-/your/plex/library}
CONFIG_FILE=${CONFIG_FILE:-/app/config/config.json}

# Python 의존성 설치 확인
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r /app/requirements.txt

# 재귀 감시 실행
echo "[INFO] Starting recursive NFO watch on ${WATCH_DIR}..."
exec /app/entrypoint/entrypoint_nfo_watch.sh --base-dir "${BASE_DIR}" --watch-dir "${WATCH_DIR}" -r
