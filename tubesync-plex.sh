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

if [ "$BASE_DIR" = "false" ]; then
    log "ERROR: BASE_DIR is set to 'false' (check how the script was invoked)"
    exit 1
fi

mkdir -p "$BASE_DIR"
CONFIG_PATH="${CONFIG_PATH:-$BASE_DIR/config/config.json}"

REPO_URL="https://github.com/kman0001/tubesync-plex.git"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
REQ_FILE="$BASE_DIR/requirements.txt"

# Files/folders to keep
KEEP=(".git" "venv" ".ffmpeg_version" "config" "json_to_nfo" "README.md" "requirements.txt" "tubesync-plex-metadata.py" "tubesync-plex.sh")

# ----------------------------
# 2. Initialize or update Git repository
# ----------------------------
if [ ! -d "$BASE_DIR/.git" ]; then
    log ".git not found, initializing repository..."
    git -C "$BASE_DIR" init
    git -C "$BASE_DIR" remote add origin "$REPO_URL"
    git -C "$BASE_DIR" fetch origin main
    git -C "$BASE_DIR" reset --hard origin/main
else
    log "Updating repository..."
    git -C "$BASE_DIR" fetch origin
    git -C "$BASE_DIR" reset --hard origin/main
fi

# ----------------------------
# 3. Python venv
# ----------------------------
VENV_PYTHON="$BASE_DIR/venv/bin/python"
VENV_PIP="$BASE_DIR/venv/bin/pip"

if [ ! -d "$BASE_DIR/venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
fi

log "Installing/updating Python dependencies..."
"$VENV_PIP" install --no-cache-dir --upgrade pip
if [ -f "$REQ_FILE" ]; then
    "$VENV_PIP" install --no-cache-dir -r "$REQ_FILE"
fi

export PATH="$BASE_DIR/venv/bin:$PATH"

# ----------------------------
# 4. Cleanup unwanted files
# ----------------------------
log "Removing unwanted files..."
for item in "$BASE_DIR"/* "$BASE_DIR"/.*; do
    [[ "$item" == "$BASE_DIR/." || "$item" == "$BASE_DIR/.." ]] && continue
    skip=false
    for k in "${KEEP[@]}"; do
        [[ "$item" == "$BASE_DIR/$k" ]] && skip=true && break
    done
    [ "$skip" = false ] && rm -rf "$item"
done

# ----------------------------
# 5. Run Python script
# ----------------------------
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    CMD="$VENV_PYTHON $PY_FILE --config $CONFIG_PATH"
    [ "$DISABLE_WATCHDOG" = true ] && CMD="$CMD --disable-watchdog"
    [ "$DEBUG" = true ] && CMD="$CMD --debug"
    [ "$DEBUG_HTTP" = true ] && CMD="$CMD --debug-http"
    exec $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
