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
    exit 1
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
    log "ERROR: --base-dir must be specified"; exit 1
fi
if [ -z "$CONFIG_PATH" ]; then
    CONFIG_PATH="$BASE_DIR/config/config.json"
fi

REPO_URL="https://github.com/kman0001/tubesync-plex.git"
mkdir -p "$BASE_DIR"
PIP_BIN="$BASE_DIR/venv/bin/pip"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
REQ_FILE="$BASE_DIR/requirements.txt"

# ----------------------------
# 2. Git shallow clone + sparse-checkout
# ----------------------------
cd "$BASE_DIR"
if [ ! -d "$BASE_DIR/.git" ]; then
    log "Initializing repository with shallow clone and sparse-checkout..."
    git init
    git remote add origin "$REPO_URL"
    git fetch --depth 1 origin main
    git sparse-checkout init --cone

    # Include only necessary folders/files
    echo "config/" > .git/info/sparse-checkout
    echo "json_to_nfo/" >> .git/info/sparse-checkout
    echo "README.md" >> .git/info/sparse-checkout
    echo "requirements.txt" >> .git/info/sparse-checkout
    echo "tubesync-plex-metadata.py" >> .git/info/sparse-checkout
    echo "tubesync-plex.sh" >> .git/info/sparse-checkout

    git checkout main
else
    log "Updating repository (shallow, sparse)..."
    git fetch --depth 1 origin main
    git checkout main  # Update only changed files
fi

# ----------------------------
# 3. Python virtual environment
# ----------------------------
if [ ! -d "$BASE_DIR/venv" ]; then
    log "Creating virtual environment..."
    if python3 -m venv "$BASE_DIR/venv" 2>/dev/null; then
        log "Python venv created successfully."
    else
        if ! command -v virtualenv &>/dev/null; then
            log "ERROR: virtualenv not found. Install with 'pip install --user virtualenv'."
            exit 1
        fi
        virtualenv "$BASE_DIR/venv"
    fi
fi

# ----------------------------
# 4. Install / update Python dependencies
# ----------------------------
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
