#!/bin/sh
set -euo pipefail

# ================================
# 기본 환경 변수
# ================================
BASE_DIR="${BASE_DIR:-/app}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/config/config.json}"

# ================================
# 1회 실행: 기존 NFO 처리 (watchdog 비활성)
# ================================
echo "[INFO] Running initial metadata sync (watchdog disabled)..."
"$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" \
  --config "$CONFIG_FILE" --disable-watchdog

# ================================
# 이후 실행: 폴더 감시
# ================================
echo "[INFO] Starting folder watch according to config..."
exec "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE"
