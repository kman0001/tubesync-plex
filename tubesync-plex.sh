#!/bin/bash
set -e

# ----------------------------
# Helper function
# ----------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# Default BASE_DIR
# ----------------------------
BASE_DIR=""
PY_FILE="tubesync-plex-metadata.py"

# ----------------------------
# Parse arguments
# ----------------------------
ARGS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir)
            BASE_DIR="$2"
            shift 2
            ;;
        --disable-watchdog|--detail|--debug-http|--debug)
            ARGS+=("$1")
            shift
            ;;
        *)
            log "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$BASE_DIR" ]; then
    log "ERROR: --base-dir must be specified"
    exit 1
fi

# ----------------------------
# Git fetch / clone
# ----------------------------
REPO_URL="https://github.com/kman0001/tubesync-plex.git"
mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

if [ ! -d ".git" ]; then
    log "Cloning repository..."
    git clone "$REPO_URL" .
else
    log "Updating repository..."
    git fetch origin
    git reset --hard origin/main
fi

# ----------------------------
# Python venv setup
# ----------------------------
VENVDIR="$BASE_DIR/venv"
PIP_BIN="$VENVDIR/bin/pip"

if [ ! -d "$VENVDIR" ]; then
    log "Creating virtual environment..."
    python3 -m venv "$VENVDIR"
else
    log "Virtual environment already exists."
fi

# ----------------------------
# Install / update dependencies
# ----------------------------
REQ_FILE="$BASE_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    log "Installing/updating Python dependencies..."
    "$PIP_BIN" install --disable-pip-version-check -q -r "$REQ_FILE"
fi

export PATH="$VENVDIR/bin:$PATH"

# ----------------------------
# Run Python script
# ----------------------------
if [ -f "$BASE_DIR/$PY_FILE" ]; then
    log "Running tubesync-plex..."
    exec "$VENVDIR/bin/python" "$BASE_DIR/$PY_FILE" --config "$BASE_DIR/config/config.json" --base-dir "$BASE_DIR" "${ARGS[@]}"
else
    log "ERROR: $PY_FILE not found."
    exit 1
fi
