#!/bin/bash

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX START"

# Use CONFIG_FILE from environment variable or default to ./config.json
CONFIG_FILE="${CONFIG_FILE:-./config.json}"

# BASE_DIR is the folder where CONFIG_FILE is located
BASE_DIR=$(dirname "$CONFIG_FILE")
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# 1. Clone or update repository
if [ ! -d "$BASE_DIR/.git" ]; then
    if [ -d "$BASE_DIR" ] && [ "$(ls -A "$BASE_DIR")" ]; then
        echo "$LOG_PREFIX $BASE_DIR exists and is not empty. Skipping clone."
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

# 2. Check if python3-venv is installed
if ! dpkg -s python3-venv &>/dev/null; then
    echo "$LOG_PREFIX Installing python3-venv..."
    apt update && apt install -y python3-venv
else
    echo "$LOG_PREFIX python3-venv is already installed."
fi

# 3. Create virtual environment if it does not exist
if [ ! -d "$BASE_DIR/venv" ]; then
    echo "$LOG_PREFIX Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
else
    echo "$LOG_PREFIX Virtual environment already exists."
fi

# 4. Install or update Python dependencies quietly, only if needed
echo "$LOG_PREFIX Installing Python dependencies..."
"$BASE_DIR/venv/bin/pip" install --upgrade-strategy only-if-needed -r "$BASE_DIR/requirements.txt" -q -q | grep -v "Requirement already satisfied"


# 5. Run tubesync-plex with the JSON configuration
if [ -f "$BASE_DIR/tubesync-plex-metadata.py" ]; then
    echo "$LOG_PREFIX Running tubesync-plex with config $CONFIG_FILE..."
    "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE"
else
    echo "$LOG_PREFIX tubesync-plex-metadata.py not found."
fi

echo "$LOG_PREFIX END"
