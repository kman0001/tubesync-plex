#!/bin/bash
set -e

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "START"

# 0. 기본값
FIXED_BASE_DIR="/tubesync-plex"
BASE_DIR="$FIXED_BASE_DIR"
CONFIG_FILE=""

# 1. 명령행 옵션 처리
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --base-dir)
        BASE_DIR="$2"
        shift
        shift
        ;;
        --config)
        CONFIG_FILE="$2"
        shift
        shift
        ;;
        *)
        shift
        ;;
    esac
done

log "BASE_DIR set to: $BASE_DIR"
log "CONFIG_FILE set to: ${CONFIG_FILE:-none}"

# 2. CONFIG_FILE 자동 탐색
if [ -z "$CONFIG_FILE" ]; then
    if [ -f "$BASE_DIR/config.json" ]; then
        CONFIG_FILE="$BASE_DIR/config.json"
    else
        log "WARNING: config.json not found in $BASE_DIR. You can pass it with --config"
    fi
fi

# 3. Repository URL
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# 4. Clone or update repository
if [ ! -d "$BASE_DIR/.git" ]; then
    if [ -d "$BASE_DIR" ] && [ "$(ls -A "$BASE_DIR")" ]; then
        log "$BASE_DIR exists and is not empty. Skipping clone."
    else
        log "Cloning repository..."
        git clone "$REPO_URL" "$BASE_DIR" || { log "ERROR: Failed to clone repository."; exit 1; }
    fi
else
    log "Checking for updates in repository..."
    pushd "$BASE_DIR" >/dev/null
    git fetch origin || { log "ERROR: git fetch failed."; popd >/dev/null; exit 1; }
    BRANCH="main"
    CHANGED_FILES=$(git diff --name-only HEAD origin/$BRANCH)
    if [ -n "$CHANGED_FILES" ]; then
        log "Updated files from GitHub:"
        echo "$CHANGED_FILES"
        git merge --no-edit origin/$BRANCH || git reset --hard origin/$BRANCH
    else
        log "No updates from GitHub."
    fi
    popd >/dev/null
fi

# 5. Check python3-venv
if ! dpkg -s python3-venv &>/dev/null; then
    log "Installing python3-venv..."
    apt update && apt install -y python3-venv || { log "ERROR: Failed to install python3-venv."; exit 1; }
fi

# 6. Create virtual environment
if [ ! -d "$BASE_DIR/venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv" || { log "ERROR: Failed to create virtualenv."; exit 1; }
fi

# 7. Install/update Python dependencies
REQ_FILE="$BASE_DIR/requirements.txt"
PIP_BIN="$BASE_DIR/venv/bin/pip"

if [ -f "$REQ_FILE" ]; then
    log "Checking Python dependencies..."
    declare -A INSTALLED
    while read -r line; do
        NAME=$(echo "$line" | cut -d= -f1)
        VER=$(echo "$line" | cut -d= -f2)
        INSTALLED["$NAME"]="$VER"
    done < <($PIP_BIN freeze)
    
    while IFS= read -r req || [[ -n "$req" ]]; do
        [[ "$req" =~ ^# ]] && continue
        PKG=$(echo "$req" | cut -d= -f1)
        REQ_VER=$(echo "$req" | cut -d= -f2)
        INST_VER="${INSTALLED[$PKG]}"
        
        if [ -z "$INST_VER" ]; then
            log "Installing new package: $PKG $REQ_VER"
            $PIP_BIN install --disable-pip-version-check -q "$req"
        elif [ "$INST_VER" != "$REQ_VER" ]; then
            log "Updating package: $PKG $INST_VER → $REQ_VER"
            $PIP_BIN install --disable-pip-version-check -q "$req"
        fi
    done < "$REQ_FILE"
    log "Python dependencies check complete."
else
    log "requirements.txt not found. Skipping pip install."
fi

# 8. Run tubesync-plex
TS_SCRIPT="$BASE_DIR/tubesync-plex-metadata.py"
if [ -f "$TS_SCRIPT" ]; then
    log "Running tubesync-plex with config $CONFIG_FILE..."
    "$BASE_DIR/venv/bin/python" "$TS_SCRIPT" --config "$CONFIG_FILE"
else
    log "ERROR: tubesync-plex-metadata.py not found in $BASE_DIR."
    exit 1
fi

log "END"
