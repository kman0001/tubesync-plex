#!/bin/bash
set -e

# ----------------------------
# Helper function
# ----------------------------
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
    exit 1
else
    log "All required system packages are installed."
fi

# ----------------------------
# 1. Parse arguments
# ----------------------------
BASE_DIR=""
DISABLE_WATCHDOG=false
DEBUG=false
DEBUG_HTTP=false
CONFIG_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --disable-watchdog) DISABLE_WATCHDOG=true; shift ;;
        --debug) DEBUG=true; shift ;;
        --debug-http) DEBUG_HTTP=true; shift ;;
        --config) CONFIG_PATH="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$BASE_DIR" ]; then
    log "ERROR: --base-dir must be specified"
    exit 1
fi

CONFIG_PATH="${CONFIG_PATH:-$BASE_DIR/config/config.json}"
mkdir -p "$BASE_DIR"

REPO_URL="https://github.com/kman0001/tubesync-plex.git"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
REQ_FILE="$BASE_DIR/requirements.txt"

# ----------------------------
# Files/folders to keep
# ----------------------------
KEEP=("config" "json_to_nfo" "README.md" "requirements.txt" "tubesync-plex-metadata.py" "tubesync-plex.sh" ".git")

# ----------------------------
# 2. Clone or update repository
# ----------------------------
cd "$BASE_DIR"

if [ ! -d ".git" ]; then
    log "Initializing repository..."
    git clone "$REPO_URL" .
else
    log "Updating repository..."
    git fetch origin
    git reset --hard origin/main
fi

# ----------------------------
# 3. Cleanup unwanted files
# ----------------------------
log "Removing unwanted files..."
for item in * .*; do
    [[ "$item" == "." || "$item" == ".." ]] && continue
    skip=false
    for k in "${KEEP[@]}"; do
        [[ "$item" == "$k" ]] && skip=true && break
    done
    if [ "$skip" = false ]; then
        rm -rf "$item"
    fi
done

# ----------------------------
# 4. Python venv (create or update)
# ----------------------------
if [ -d "$BASE_DIR/venv" ]; then
    log "Virtual environment exists. Upgrading/installing dependencies..."
else
    log "Creating new virtual environment..."
    if python3 -m venv "$BASE_DIR/venv"; then
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
fi

PIP_BIN="$BASE_DIR/venv/bin/pip"
"$PIP_BIN" install --upgrade pip --disable-pip-version-check -q
if [ -f "$REQ_FILE" ]; then
    "$PIP_BIN" install --disable-pip-version-check -q -r "$REQ_FILE"
fi

export PATH="$BASE_DIR/venv/bin:$PATH"

# ----------------------------
# 5. Run Python script
# ----------------------------
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    CMD="$BASE_DIR/venv/bin/python $PY_FILE --config $CONFIG_PATH"

    [ "$DISABLE_WATCHDOG" = true ] && CMD="$CMD --disable-watchdog"
    [ "$DEBUG" = true ] && CMD="$CMD --debug"
    [ "$DEBUG_HTTP" = true ] && CMD="$CMD --debug-http"

    exec $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
