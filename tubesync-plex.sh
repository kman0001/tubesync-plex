#!/bin/bash

CONFIG_FILE="./config.ini"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX START"

# config.ini에서 base_dir 읽기
BASE_DIR=$(grep -E "^base_dir" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d ' ')

if [ -z "$BASE_DIR" ]; then
    echo "$LOG_PREFIX Error: base_dir not defined in $CONFIG_FILE"
    exit 1
fi

REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# 1. Clone or update repository
if [ ! -d "$BASE_DIR/.git" ]; then
    if [ -d "$BASE_DIR" ] && [ "$(ls -A "$BASE_DIR")" ]; then
        echo "$LOG_PREFIX $BASE_DIR already exists and is not empty. Skipping clone."
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

# 2. Check and install python3-venv if missing
if ! dpkg -s python3-venv &>/dev/null; then
    echo "$LOG_PREFIX Installing python3-venv..."
    apt update && apt install -y python3-venv
else
    echo "$LOG_PREFIX python3-venv already installed."
fi

# 3. Create virtual environment
if [ ! -d "$BASE_DIR/venv" ]; then
    echo "$LOG_PREFIX Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
else
    echo "$LOG_PREFIX Virtual environment already exists."
fi

# 4. Install / update Python dependencies
echo "$LOG_PREFIX Installing Python dependencies..."
"$BASE_DIR/venv/bin/pip" install --upgrade pip &>/dev/null
REQ_UPDATE=$("$BASE_DIR/venv/bin/pip" install -r "$BASE_DIR/requirements.txt" 2>&1 | grep "Requirement")
if [ -z "$REQ_UPDATE" ]; then
    echo "$LOG_PREFIX Python dependencies already up-to-date."
fi

# 5. Run tubesync-plex
if [ -f "$BASE_DIR/tubesync-plex-metadata.py" ]; then
    echo "$LOG_PREFIX Running tubesync-plex..."
    "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --all
else
    echo "$LOG_PREFIX tubesync-plex-metadata.py not found. Please check repository."
fi

echo "$LOG_PREFIX END"
