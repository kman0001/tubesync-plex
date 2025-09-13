#!/bin/bash

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX START"

# 0. Config file
CONFIG_FILE="${CONFIG_FILE:-./config.json}"

# 1. Base directory = folder containing config file
BASE_DIR=$(dirname "$(realpath "$CONFIG_FILE")")

# 2. Repository URL
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# 3. Clone or update repository
if [ ! -d "$BASE_DIR/.git" ]; then
    if [ -d "$BASE_DIR" ] && [ "$(ls -A "$BASE_DIR")" ]; then
        echo "$LOG_PREFIX $BASE_DIR exists and is not empty. Skipping clone."
    else
        echo "$LOG_PREFIX Cloning repository..."
        git clone "$REPO_URL" "$BASE_DIR" || { echo "$LOG_PREFIX ERROR: Failed to clone repository."; exit 1; }
    fi
else
    echo "$LOG_PREFIX Checking for updates in repository..."
    pushd "$BASE_DIR" >/dev/null || { echo "$LOG_PREFIX ERROR: Cannot cd to $BASE_DIR"; exit 1; }

    git fetch origin || { echo "$LOG_PREFIX ERROR: git fetch failed."; popd >/dev/null; exit 1; }

    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    CHANGED_FILES=$(git diff --name-only HEAD origin/$BRANCH)

    if [ -n "$CHANGED_FILES" ]; then
        echo "$LOG_PREFIX Updated files from GitHub:"
        echo "$CHANGED_FILES"
        git merge --no-edit origin/$BRANCH || git reset --merge origin/$BRANCH
    else
        echo "$LOG_PREFIX No updates from GitHub."
    fi
    popd >/dev/null
fi

# 4. Check python3-venv
if ! dpkg -s python3-venv &>/dev/null; then
    apt update && apt install -y python3-venv || { echo "$LOG_PREFIX ERROR: Failed to install python3-venv."; exit 1; }
fi

# 5. Create virtual environment
[ -d "$BASE_DIR/venv" ] || python3 -m venv "$BASE_DIR/venv" || { echo "$LOG_PREFIX ERROR: Failed to create virtualenv."; exit 1; }

# 6. Install/update Python dependencies (quiet, only if needed)
REQ_FILE_PATH="$BASE_DIR/requirements.txt"

if [ -f "$REQ_FILE_PATH" ]; then
    echo "$LOG_PREFIX Checking Python dependencies..."
    PIP_BIN="$BASE_DIR/venv/bin/pip"

    # Get installed packages
    declare -A INSTALLED_PACKAGES
    while read -r line; do
        NAME=$(echo "$line" | cut -d= -f1)
        VER=$(echo "$line" | cut -d= -f3)
        INSTALLED_PACKAGES["$NAME"]="$VER"
    done < <($PIP_BIN list --format=freeze)

    # Process each package in requirements.txt
    while IFS= read -r req_line || [[ -n "$req_line" ]]; do
        [[ "$req_line" =~ ^# ]] && continue  # skip comments
        PKG=$(echo "$req_line" | cut -d= -f1)
        REQ_VER=$(echo "$req_line" | cut -d= -f3)
        INST_VER="${INSTALLED_PACKAGES[$PKG]}"

        if [ -z "$INST_VER" ]; then
            echo "$LOG_PREFIX Installing new package: $PKG $REQ_VER"
            $PIP_BIN install --disable-pip-version-check -q "$req_line" >/dev/null 2>&1
        elif [ "$INST_VER" != "$REQ_VER" ]; then
            echo "$LOG_PREFIX Updating package: $PKG $INST_VER → $REQ_VER"
            $PIP_BIN install --disable-pip-version-check -q "$req_line" >/dev/null 2>&1
        fi
    done < "$REQ_FILE_PATH"

    echo "$LOG_PREFIX Python dependencies check complete."
else
    echo "$LOG_PREFIX requirements.txt not found. Skipping pip install."
fi

# 7. Run tubesync-plex
if [ -f "$BASE_DIR/tubesync-plex-metadata.py" ]; then
    echo "$LOG_PREFIX Running tubesync-plex with config $CONFIG_FILE..."
    "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE" >/dev/null 2>&1 || { echo "$LOG_PREFIX ERROR: tubesync-plex-metadata.py execution failed."; exit 1; }
else
    echo "$LOG_PREFIX ERROR: tubesync-plex-metadata.py not found in $BASE_DIR."
    exit 1
fi

echo "$LOG_PREFIX END"
