#!/bin/sh
set -euo pipefail

# ================================
# 기본 환경 변수
# ================================
BASE_DIR="${BASE_DIR:-/app}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/config/config.json}"
DEBOUNCE_DELAY="${DEBOUNCE_DELAY:-2}"

# ================================
# Python 의존성 설치 확인
# ================================
"$BASE_DIR/venv/bin/pip" install --upgrade pip
"$BASE_DIR/venv/bin/pip" install -r "$BASE_DIR/requirements.txt"

# ================================
# NFO 감시 스크립트 실행
# ================================
echo "[INFO] Starting recursive NFO watch..."
exec "$BASE_DIR/entrypoint/entrypoint_nfo_watch.sh"
