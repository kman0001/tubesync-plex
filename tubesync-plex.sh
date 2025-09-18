#!/bin/bash
set -e

# ----------------------------
# Helper
# ----------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# Parse arguments
# ----------------------------
BASE_DIR=""
DISABLE_WATCHDOG=false
DEBUG_HTTP=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --disable-watchdog) DISABLE_WATCHDOG=true; shift ;;
        --debug-http) DEBUG_HTTP=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$BASE_DIR" ]; then
    echo "ERROR: --base-dir must be specified"
    exit 1
fi

mkdir -p "$BASE_DIR"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
PIP_BIN="$BASE_DIR/venv/bin/pip"
REQ_FILE="$BASE_DIR/requirements.txt"

# ----------------------------
# Git clone / fetch & reset
# ----------------------------
cd "$BASE_DIR"
if [ ! -d ".git" ]; then
    log "Cloning repository..."
    git clone https://github.com/kman0001/tubesync-plex.git .
else
    log "Updating repository..."
    git fetch origin
    git reset --hard origin/main
fi

# ----------------------------
# Python venv
# ----------------------------
if [ ! -d "venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv venv || virtualenv venv
fi

log "Installing Python dependencies..."
"$PIP_BIN" install --disable-pip-version-check -q -r "$REQ_FILE"

export PATH="$BASE_DIR/venv/bin:$PATH"

# ----------------------------
# Run Python
# ----------------------------
CMD="$BASE_DIR/venv/bin/python $PY_FILE --config $BASE_DIR/config/config.json --base-dir $BASE_DIR"
[ "$DISABLE_WATCHDOG" = true ] && CMD="$CMD --disable-watchdog"
[ "$DEBUG_HTTP" = true ] && CMD="$CMD --debug-http --detail"

exec $CMD
