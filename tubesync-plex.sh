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
# 1. Clone or always update repository
# -----------------------------
if [ ! -d "$BASE_DIR/.git" ]; then
    echo "Cloning repository..."
    git clone "$REPO_URL" "$BASE_DIR"
else
    echo "Updating repository..."
    cd "$BASE_DIR" || exit 1
    git fetch origin
    git reset --hard origin/main
fi

# -----------------------------
# 2. Check python3-venv
# -----------------------------
if ! dpkg -s python3-venv &>/dev/null; then
    echo "Installing python3-venv..."
    apt update && apt install -y python3-venv
fi

# -----------------------------
# 3. Create virtual environment
# -----------------------------
if [ ! -d "$BASE_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
fi

PIP_BIN="$BASE_DIR/venv/bin/pip"

# -----------------------------
# 4. Install Python dependencies
# -----------------------------
REQ_FILE="$BASE_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
    echo "Installing Python dependencies..."
    "$PIP_BIN" install --upgrade pip --quiet
    "$PIP_BIN" install -r "$REQ_FILE" --quiet
fi

# -----------------------------
# 5. Run Python script
# -----------------------------
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
if [ -f "$PY_FILE" ]; then
    echo "Running tubesync-plex..."
    exec "$BASE_DIR/venv/bin/python" "$PY_FILE" --config "$CONFIG_FILE"
else
    echo "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
