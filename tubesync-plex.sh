#!/bin/bash

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX START"

CONFIG_FILE="./config.ini"
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# 1. Clone or update repository
if [ ! -d ".git" ]; then
    if [ "$(ls -A .)" ]; then
        echo "$LOG_PREFIX Directory exists and not empty. Skipping clone."
    else
        echo "$LOG_PREFIX Cloning repository..."
        git clone "$REPO_URL" .
    fi
else
    echo "$LOG_PREFIX Updating repository..."
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
if [ ! -d "venv" ]; then
    echo "$LOG_PREFIX Creating virtual environment..."
    python3 -m venv venv
else
    echo "$LOG_PREFIX Virtual environment already exists."
fi

# 4. Install / update Python dependencies
echo "$LOG_PREFIX Installing Python dependencies..."
./venv/bin/pip install --upgrade pip &>/dev/null
REQ_UPDATE=$(./venv/bin/pip install -r requirements.txt 2>&1 | grep "Requirement")
if [ -z "$REQ_UPDATE" ]; then
    echo "$LOG_PREFIX Python dependencies already up-to-date."
fi

# 5. Run tubesync-plex
if [ -f "tubesync-plex-metadata.py" ]; then
    echo "$LOG_PREFIX Running tubesync-plex..."
    ./venv/bin/python tubesync-plex-metadata.py --all
else
    echo "$LOG_PREFIX tubesync-plex-metadata.py not found."
fi

echo "$LOG_PREFIX END"
