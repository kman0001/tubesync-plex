#!/bin/bash
set -e

# ----------------------------
# Helper function
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
    log "Please install them using your system's package manager before running this script."
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
PY_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir)
            BASE_DIR="$2"
            shift 2
            ;;
        --disable-watchdog)
            DISABLE_WATCHDOG=true
            PY_ARGS+=("$1")
            shift
            ;;
        --debug-http)
            DEBUG_HTTP=true
            PY_ARGS+=("$1")
            shift
            ;;
        --debug|--detail)
            PY_ARGS+=("$1")
            shift
            ;;
        --config)
            PY_ARGS+=("$1" "$2")
            shift 2
            ;;
        *)
            log "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Set default base dir if not provided
if [ -z "$BASE_DIR" ]; then
    log "INFO: --base-dir not specified, using /app as default"
    BASE_DIR="/app"
fi

REPO_URL="https://github.com/kman0001/tubesync-plex.git"
mkdir -p "$BASE_DIR"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
PIP_BIN="$BASE_DIR/venv/bin/pip"

# ----------------------------
# Git clone or update
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
# Python venv
# ----------------------------
if [ ! -d "$BASE_DIR/venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
else
    log "Virtual environment already exists."
fi

# ----------------------------
# Install / update Python dependencies
# ----------------------------
REQ_FILE="$BASE_DIR/requirements.txt"
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
    CMD="$BASE_DIR/venv/bin/python $PY_FILE --config $BASE_DIR/config/config.json --base-dir $BASE_DIR ${PY_ARGS[*]}"
    exec $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
