#!/bin/bash
set -e

# ----------------------------
# Helper function
# ----------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# Parse arguments
# ----------------------------
BASE_DIR=""
DISABLE_WATCHDOG=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --disable-watchdog) DISABLE_WATCHDOG=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$BASE_DIR" ]; then
    echo "ERROR: --base-dir must be specified"
    exit 1
fi

REPO_URL="https://github.com/kman0001/tubesync-plex.git"
mkdir -p "$BASE_DIR"
PIP_BIN="$BASE_DIR/venv/bin/pip"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
REQ_FILE="$BASE_DIR/requirements.txt"

# ----------------------------
# 1. Git fetch + reset
# ----------------------------
cd "$BASE_DIR"
if [ ! -d "$BASE_DIR/.git" ]; then
    log "Initializing git repository..."
    git init
    git remote add origin "$REPO_URL"
    git fetch origin
    git reset --hard origin/main
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
    python3 -m venv "$BASE_DIR/venv"
else
    log "Virtual environment already exists."
fi

# ----------------------------
# 3. Install / update Python dependencies
# ----------------------------
if [ -f "$REQ_FILE" ]; then
    log "Installing/updating Python dependencies..."
    declare -A INSTALLED
    while read -r line; do
        NAME=$(echo "$line" | cut -d= -f1)
        VER=$(echo "$line" | cut -d= -f3)
        INSTALLED["$NAME"]="$VER"
    done < <("$PIP_BIN" freeze)

    while IFS= read -r req || [[ -n "$req" ]]; do
        [[ "$req" =~ ^# ]] && continue
        PKG=$(echo "$req" | cut -d= -f1)
        REQ_VER=$(echo "$req" | cut -d= -f3)
        INST_VER="${INSTALLED[$PKG]}"
        if [ -z "$INST_VER" ] || [ "$INST_VER" != "$REQ_VER" ]; then
            log "Installing/updating package: $PKG $REQ_VER"
            "$PIP_BIN" install --disable-pip-version-check -q "$req"
        fi
    done < "$REQ_FILE"
fi

# ----------------------------
# 4. Run Python script
# ----------------------------
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    CMD="$BASE_DIR/venv/bin/python $PY_FILE --config $BASE_DIR/config.json"
    if [ "$DISABLE_WATCHDOG" = true ]; then
        CMD="$CMD --disable-watchdog"
    fi
    exec $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
