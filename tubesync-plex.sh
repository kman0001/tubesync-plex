#!/bin/bash
set -e

# ----------------------------
# Helper
# ----------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# Check required system packages
# ----------------------------
REQUIRED_PACKAGES=(git python3 pip3)
MISSING_PACKAGES=()

for PKG in "${REQUIRED_PACKAGES[@]}"; do
    if ! command -v "$PKG" &>/dev/null; then
        MISSING_PACKAGES+=("$PKG")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    log "ERROR: Missing required system packages: ${MISSING_PACKAGES[*]}"
    log "Please install them manually before running this script."
    exit 1
fi
log "All required system packages are installed."

# ----------------------------
# Parse arguments
# ----------------------------
BASE_DIR=""
DISABLE_WATCHDOG=false
DEBUG_HTTP=false
DETAIL=false
DEBUG=false
CONFIG_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --disable-watchdog) DISABLE_WATCHDOG=true; shift ;;
        --debug-http) DEBUG_HTTP=true; shift ;;
        --detail) DETAIL=true; shift ;;
        --debug) DEBUG=true; shift ;;
        --config) CONFIG_FILE="$2"; shift 2 ;;
        *) log "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$CONFIG_FILE" ]; then
    log "ERROR: --config must be specified"
    exit 1
fi

if [ -z "$BASE_DIR" ]; then
    BASE_DIR="/app"
fi

mkdir -p "$BASE_DIR"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
REQ_FILE="$BASE_DIR/requirements.txt"
PIP_BIN="$BASE_DIR/venv/bin/pip"

# ----------------------------
# Git clone / fetch + reset
# ----------------------------
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

cd "$BASE_DIR"
if [ ! -d "$BASE_DIR/.git" ]; then
    log "Cloning repository..."
    git clone "$REPO_URL" . 
else
    log "Updating repository..."
    git fetch origin
    git reset --hard origin/main
fi

# ----------------------------
# Python venv
# ----------------------------
if [ ! -d "$BASE_DIR/venv" ]; then
    log "Creating virtual environment..."
    if python3 -m venv "$BASE_DIR/venv" 2>/dev/null; then
        log "Python venv created successfully."
    else
        log "Python venv module not available, trying virtualenv..."
        if ! command -v virtualenv &>/dev/null; then
            log "ERROR: virtualenv not found. Please install it using 'pip install --user virtualenv'."
            exit 1
        fi
        virtualenv "$BASE_DIR/venv"
        log "Virtual environment created via virtualenv."
    fi
else
    log "Virtual environment already exists."
fi

# ----------------------------
# Install/update dependencies
# ----------------------------
if [ -f "$REQ_FILE" ]; then
    log "Installing/updating Python dependencies..."
    "$PIP_BIN" install --disable-pip-version-check -q -r "$REQ_FILE"
fi

export PATH="$BASE_DIR/venv/bin:$PATH"

# ----------------------------
# Run Python script
# ----------------------------
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    CMD="$BASE_DIR/venv/bin/python $PY_FILE --config $CONFIG_FILE"

    [ "$DISABLE_WATCHDOG" = true ] && CMD="$CMD --disable-watchdog"
    [ "$DEBUG_HTTP" = true ] && CMD="$CMD --debug-http"
    [ "$DETAIL" = true ] && CMD="$CMD --detail"
    [ "$DEBUG" = true ] && CMD="$CMD --debug"
    [ "$BASE_DIR" != "/app" ] && CMD="$CMD --base-dir $BASE_DIR"

    exec $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
