#!/bin/sh
set -euo pipefail

# ================================
# 기본 환경 변수
# ================================
BASE_DIR="${BASE_DIR:-/app}"
CONFIG_FILE="${CONFIG_FILE:-$BASE_DIR/config/config.json}"

# ================================
# Python 의존성 설치 확인
# ================================
#"$BASE_DIR/venv/bin/pip" install --upgrade pip
#"$BASE_DIR/venv/bin/pip" install -r "$BASE_DIR/requirements.txt"

# ================================
# TubeSync Plex Metadata 실행
# ================================
exec "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE"
