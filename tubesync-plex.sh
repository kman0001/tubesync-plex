#!/bin/bash
set -e

# -----------------------------
# Variables
# -----------------------------
BASE_DIR="${BASE_DIR:-$(pwd)}"
REQ_FILE="$BASE_DIR/requirements.txt"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
VENV_DIR="$BASE_DIR/venv"
DISABLE_WATCHDOG=${DISABLE_WATCHDOG:-false}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# -----------------------------
# 1. Update repository
# -----------------------------
log "Updating repository..."
cd "$BASE_DIR"
git fetch --all
git reset --hard origin/main

# -----------------------------
# 2. Create virtual environment
# -----------------------------
if [ ! -d "$VENV_DIR" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

PIP_BIN="$VENV_DIR/bin/pip"

# -----------------------------
# 3. Install/update Python dependencies quietly
# -----------------------------
log "Installing/updating Python dependencies..."

INSTALLED=$("$PIP_BIN" freeze)

while IFS= read -r req || [[ -n "$req" ]]; do
    [[ "$req" =~ ^# ]] && continue
    PKG=$(echo "$req" | cut -d= -f1)
    REQ_VER=$(echo "$req" | cut -d= -f3)
    INST_VER=$(echo "$INSTALLED" | grep -i "^$PKG==" | cut -d= -f3)
    if [ -z "$INST_VER" ] || [ "$INST_VER" != "$REQ_VER" ]; then
        log "Installing/updating package: $PKG $REQ_VER"
        "$PIP_BIN" install --disable-pip-version-check -q "$req"
    fi
done < "$REQ_FILE"

# -----------------------------
# 4. Run Python script
# -----------------------------
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    CMD="$VENV_DIR/bin/python $PY_FILE --config $BASE_DIR/config.json"
    if [ "$DISABLE_WATCHDOG" = true ]; then
        CMD="$CMD --disable-watchdog"
    fi
    exec $CMD
else
    log "Python script not found: $PY_FILE"
    exit 1
fi
