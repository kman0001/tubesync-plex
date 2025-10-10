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

# ----------------------------
# Default BASE_DIR
# ----------------------------
if [ -z "$BASE_DIR" ]; then
    log "ERROR: --base-dir must be specified"
    exit 1
fi

# ----------------------------
# Default config path
# ----------------------------
if [ -z "$CONFIG_PATH" ]; then
    CONFIG_PATH="$BASE_DIR/config/config.json"
fi

REPO_URL="https://github.com/kman0001/tubesync-plex.git"
mkdir -p "$BASE_DIR"
PIP_BIN="$BASE_DIR/venv/bin/pip"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
REQ_FILE="$BASE_DIR/requirements.txt"

# ----------------------------
# 1. Git clone / fetch + sparse-checkout
# ----------------------------
cd "$BASE_DIR"
if [ ! -d "$BASE_DIR/.git" ]; then
    log "Initializing repository with sparse-checkout..."
    git init
    git remote add origin "$REPO_URL"
    git fetch origin main
    git sparse-checkout init --cone

    # 체크아웃할 파일/폴더 지정 (전체 포함 + 제외 파일)
    echo "/*" > .git/info/sparse-checkout       # 전체 포함
    # .으로 시작하는 모든 파일/폴더 제외
    echo "!/.*" >> .git/info/sparse-checkout
    echo "!/Dockerfile" >> .git/info/sparse-checkout  # 제외
    echo "!/entrypoint.sh" >> .git/info/sparse-checkout  # 제외
    echo "!/ffmpeg/*" >> .git/info/sparse-checkout  # 제외

    git checkout main
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
# 3. Install / update Python dependencies
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
    CMD="$BASE_DIR/venv/bin/python $PY_FILE --config $CONFIG_PATH"

    [ "$DISABLE_WATCHDOG" = true ] && CMD="$CMD --disable-watchdog"
    [ "$DEBUG" = true ] && CMD="$CMD --debug"
    [ "$DEBUG_HTTP" = true ] && CMD="$CMD --debug-http"

    exec $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
