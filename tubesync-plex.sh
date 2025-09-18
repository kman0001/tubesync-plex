#!/bin/bash
set -e

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# 0. Check required system packages
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
    log "Please install them before running this script."
    exit 1
else
    log "All required system packages are installed."
fi

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

# ----------------------------
# Ensure BASE_DIR is provided
# ----------------------------
if [ -z "$BASE_DIR" ]; then
    log "ERROR: --base-dir must be specified when running tubesync-plex.sh"
    log "Example: $0 --base-dir /volume1/docker/tubesync/tubesync-plex"
    exit 1
fi

mkdir -p "$BASE_DIR"
PIP_BIN="$BASE_DIR/venv/bin/pip"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
REQ_FILE="$BASE_DIR/requirements.txt"
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# ----------------------------
# 1. Git clone / fetch
# ----------------------------
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
# 2. Python venv
# ----------------------------
if [ ! -d "$BASE_DIR/venv" ]; then
    log "Creating virtual environment..."
    if python3 -m venv "$BASE_DIR/venv" 2>/dev/null; then
        log "Python venv created."
    else
        log "Trying virtualenv..."
        if ! command -v virtualenv &>/dev/null; then
            log "ERROR: virtualenv not found. Install it via 'pip install --user virtualenv'"
            exit 1
        fi
        virtualenv "$BASE_DIR/venv"
    fi
else
    log "Virtual environment already exists."
fi

# ----------------------------
# 3. Install dependencies
# ----------------------------
log "Installing/updating Python dependencies..."
if [ -f "$REQ_FILE" ]; then
    "$PIP_BIN" install --disable-pip-version-check -q -r "$REQ_FILE"
fi
export PATH="$BASE_DIR/venv/bin:$PATH"

# ----------------------------
# 4. Run Python script
# ----------------------------
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    CMD_ENV="BASE_DIR=$BASE_DIR"
    CMD="$BASE_DIR/venv/bin/python $PY_FILE --config $BASE_DIR/config/config.json ${EXTRA_PY_ARGS[*]}"

    if [ "$DISABLE_WATCHDOG" = true ]; then
        CMD="$CMD --disable-watchdog"
    fi
    if [ "$DEBUG_HTTP" = true ]; then
        CMD="$CMD --debug-http"
    fi

    exec $CMD_ENV $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
