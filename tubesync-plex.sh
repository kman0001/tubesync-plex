#!/bin/bash

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX START"

# CONFIG_FILE을 환경변수로 받거나 기본값 ./config.json
CONFIG_FILE="${CONFIG_FILE:-./config.json}"

BASE_DIR=$(dirname "$CONFIG_FILE")
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# 1. Clone or update repo
if [ ! -d "$BASE_DIR/.git" ]; then
    if [ -d "$BASE_DIR" ] && [ "$(ls -A "$BASE_DIR")" ]; then
        echo "$LOG_PREFIX $BASE_DIR exists and not empty. Skipping clone."
    else
        echo "$LOG_PREFIX Cloning repository..."
        git clone "$REPO_URL" "$BASE_DIR"
    fi
else
    echo "$LOG_PREFIX Updating repository..."
    cd "$BASE_DIR" || exit 1
    git reset --hard
    git pull
fi

# 2. Check python3-venv
if ! dpkg -s python3-venv &>/dev/null; then
    echo "$LOG_PREFIX Installing python3-venv..."
    apt update && apt install -y python3-venv
else
    echo "$LOG_PREFIX python3-venv already installed."
fi

# 3. Create venv
if [ ! -d "$BASE_DIR/venv" ]; then
    echo "$LOG_PREFIX Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
else
    echo "$LOG_PREFIX Virtual environment exists."
fi

# 4. Install dependencies
echo "$LOG_PREFIX Installing Python dependencies..."
"$BASE_DIR/venv/bin/pip" install --upgrade pip &>/dev/null
"$BASE_DIR/venv/bin/pip" install -r "$BASE_DIR/requirements.txt" &>/dev/null

# 5. Run metadata sync
if [ -f "$BASE_DIR/tubesync-plex-metadata.py" ]; then
    echo "$LOG_PREFIX Running tubesync-plex..."
    "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py"
else
    echo "$LOG_PREFIX tubesync-plex-metadata.py not found."
fi

echo "$LOG_PREFIX END"
