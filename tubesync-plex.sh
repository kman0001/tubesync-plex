#!/bin/bash

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX START"

BASE_DIR="/your/dir/to/tubesync-plex"
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# 1. Clone repository if not exists
if [ ! -d "$BASE_DIR/.git" ]; then
    if [ -d "$BASE_DIR" ] && [ "$(ls -A "$BASE_DIR")" ]; then
        echo "$LOG_PREFIX $BASE_DIR already exists and is not empty. Skipping clone."
    else
        echo "$LOG_PREFIX Cloning repository..."
        git clone "$REPO_URL" "$BASE_DIR"
    fi
fi

cd "$BASE_DIR" || exit 1

# 2. Check for updates
echo "$LOG_PREFIX Checking for updates..."
git fetch origin
LOCAL_HASH=$(git rev-parse HEAD)
REMOTE_HASH=$(git rev-parse origin/main)

UPDATED=false
if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
    echo "$LOG_PREFIX Remote changes detected. Pulling updates..."
    git reset --hard &>/dev/null
    git pull &>/dev/null
    UPDATED=true
else
    echo "$LOG_PREFIX Local repository is up-to-date."
fi

# 3. Check if requirements.txt changed
REQ_HASH_FILE="$BASE_DIR/.requirements_hash"
if [ -f "$BASE_DIR/requirements.txt" ]; then
    CURRENT_REQ_HASH=$(md5sum "$BASE_DIR/requirements.txt" | awk '{print $1}')
    LAST_REQ_HASH=""
    [ -f "$REQ_HASH_FILE" ] && LAST_REQ_HASH=$(cat "$REQ_HASH_FILE")
    if [ "$CURRENT_REQ_HASH" != "$LAST_REQ_HASH" ]; then
        echo "$LOG_PREFIX requirements.txt changed."
        UPDATED=true
        echo "$CURRENT_REQ_HASH" > "$REQ_HASH_FILE"
    fi
fi

# 4. Ensure python3-venv
if ! dpkg -s python3-venv &>/dev/null; then
    echo "$LOG_PREFIX Installing python3-venv..."
    apt update &>/dev/null && apt install -y python3-venv &>/dev/null
else
    echo "$LOG_PREFIX python3-venv already installed."
fi

# 5. Create virtual environment if missing
if [ ! -d "$BASE_DIR/venv" ]; then
    echo "$LOG_PREFIX Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
fi

# 6. Update Python dependencies only if updated
if [ "$UPDATED" = true ]; then
    echo "$LOG_PREFIX Updating Python dependencies..."
    "$BASE_DIR/venv/bin/pip" install --upgrade pip &>/dev/null
    "$BASE_DIR/venv/bin/pip" install -r "$BASE_DIR/requirements.txt" &>/dev/null
    echo "$LOG_PREFIX Python dependencies updated."
else
    echo "$LOG_PREFIX Python dependencies already up-to-date."
fi

# 7. Run tubesync-plex
if [ -f "$BASE_DIR/tubesync-plex-metadata.py" ]; then
    echo "$LOG_PREFIX Running tubesync-plex..."
    "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --all
else
    echo "$LOG_PREFIX tubesync-plex-metadata.py not found. Please check repository."
fi

echo "$LOG_PREFIX END"
