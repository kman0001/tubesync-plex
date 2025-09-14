#!/bin/bash
set -e

# -----------------------------
# 0. Parse external option --base-dir
# -----------------------------
BASE_DIR=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir)
            BASE_DIR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [ -z "$BASE_DIR" ]; then
    echo "ERROR: --base-dir must be specified"
    exit 1
fi

CONFIG_FILE="$BASE_DIR/config.json"
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

mkdir -p "$BASE_DIR"

# -----------------------------
# Helper function for logs
# -----------------------------
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# -----------------------------
# 1. Clone or fetch/reset repository
# -----------------------------
cd "$BASE_DIR"

if [ ! -d "$BASE_DIR/.git" ]; then
    log "Initializing git repository..."
    git init
    git remote add origin "$REPO_URL"
    if ! git fetch origin; then
        log "git fetch failed, running git clone..."
        cd ..
        rm -rf "$BASE_DIR"
        git clone "$REPO_URL" "$BASE_DIR"
        cd "$BASE_DIR"
    else
        git reset --hard origin/main
    fi
else
    log "Updating repository..."
    git fetch origin
    git reset --hard origin/main
fi

# -----------------------------
# 2. Check python3-venv
# -----------------------------
if ! dpkg -s python3-venv &>/dev/null; then
    log "Installing python3-venv..."
    apt update && apt install -y python3-venv
else
    log "python3-venv already installed."
fi

# -----------------------------
# 3. Create virtual environment if not exists
# -----------------------------
if [ ! -d "$BASE_DIR/venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
else
    log "Virtual environment already exists."
fi

PIP_BIN="$BASE_DIR/venv/bin/pip"
REQ_FILE="$BASE_DIR/requirements.txt"

# -----------------------------
# 4. Install / update Python dependencies
# -----------------------------
if [ -f "$REQ_FILE" ]; then
    log "Checking Python dependencies..."

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

        if [ -z "$INST_VER" ]; then
            log "Installing new package: $PKG $REQ_VER"
            "$PIP_BIN" install --disable-pip-version-check "$req"
        elif [ "$INST_VER" != "$REQ_VER" ]; then
            log "Updating package: $PKG $INST_VER → $REQ_VER"
            "$PIP_BIN" install --disable-pip-version-check "$req"
        fi
        # 동일 버전 패키지는 pip 호출 안 함 → 로그 없음
    done < "$REQ_FILE"

    log "Python dependencies check complete."
else
    log "requirements.txt not found. Skipping pip install."
fi

# -----------------------------
# 5. Run tubesync-plex-metadata.py
# -----------------------------
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    exec "$BASE_DIR/venv/bin/python" "$PY_FILE" --config "$CONFIG_FILE"
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
