#!/bin/sh
set -e

# 환경 변수
BASE_DIR=${BASE_DIR:-/app}
WATCH_DIR=${WATCH_DIR:-/downloads}
CONFIG_FILE=${CONFIG_FILE:-/app/config/config.json}

# Python 의존성 설치 확인
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r /app/requirements.txt

# 1회 기존 NFO 처리
echo "[INFO] Processing existing NFO files in ${WATCH_DIR}..."
./entrypoint_nfo_watch.sh --base-dir "${BASE_DIR}" --watch-dir "${WATCH_DIR}" --once

# 재귀 감시 실행
echo "[INFO] Starting recursive NFO watch on ${WATCH_DIR}..."
exec ./entrypoint_nfo_watch.sh --base-dir "${BASE_DIR}" --watch-dir "${WATCH_DIR}" -r
