#!/bin/bash

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
echo "$LOG_PREFIX START"

# Config file
CONFIG_FILE="${CONFIG_FILE:-./config.json}"

# Base directory = folder containing config file
BASE_DIR=$(dirname "$(realpath "$CONFIG_FILE")")

REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# 1. Clone or update repository
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
    BRANCH="main"
    CHANGED_FILES=$(git diff --name-only HEAD origin/$BRANCH)
    if [ -n "$CHANGED_FILES" ]; then
        echo "$LOG_PREFIX Updated files from GitHub:"
        echo "$CHANGED_FILES"
        git merge --no-edit origin/$BRANCH || git reset --hard origin/$BRANCH
    else
        echo "$LOG_PREFIX No updates from GitHub."
    fi
    popd >/dev/null
fi

# 2. Check python3-venv
dpkg -s python3-venv &>/dev/null || { apt update && apt install -y python3-venv || { echo "$LOG_PREFIX ERROR: Failed to install python3-venv."; exit 1; }; }

# 3. Create virtual environment
[ -d "$BASE_DIR/venv" ] || python3 -m venv "$BASE_DIR/venv" || { echo "$LOG_PREFIX ERROR: Failed to create virtualenv."; exit 1; }

# 4. Locate requirements.txt and corresponding hash file
REQ_FILE="${REQ_FILE:-$BASE_DIR/requirements.txt}"  # environment variable override possible
REQ_FILE_PATH=$(realpath "$REQ_FILE")
REQ_DIR=$(dirname "$REQ_FILE_PATH")
HASH_FILE="$REQ_DIR/.requirements.hash"

# Ensure hash file exists
[ -f "$HASH_FILE" ] || touch "$HASH_FILE"

if [ -f "$REQ_FILE_PATH" ]; then
    echo "$LOG_PREFIX Checking Python dependencies..."
    PIP_BIN="$BASE_DIR/venv/bin/pip"

    CURRENT_HASH=$(sha256sum "$REQ_FILE_PATH" | awk '{print $1}')
    PREV_HASH=$(cat "$HASH_FILE" 2>/dev/null || echo "")

    INSTALL_NEEDED=false

    # Get installed packages
    declare -A INSTALLED_PACKAGES
    while read -r line; do
        NAME=$(echo "$line" | cut -d= -f1)
        VER=$(echo "$line" | cut -d= -f3)
        INSTALLED_PACKAGES["$NAME"]="$VER"
    done < <($PIP_BIN freeze)

    if [ "$CURRENT_HASH" != "$PREV_HASH" ]; then
        INSTALL_NEEDED=true
        echo "$CURRENT_HASH" > "$HASH_FILE"
    else
        # Check missing or outdated packages
        MISSING=$(comm -23 <(sort "$REQ_FILE_PATH") <($PIP_BIN freeze | cut -d= -f1 | sort))
        OUTDATED=$($PIP_BIN list --outdated --format=freeze | cut -d= -f1)
        [ -n "$MISSING" ] || [ -n "$OUTDATED" ] && INSTALL_NEEDED=true
    fi

    if [ "$INSTALL_NEEDED" = true ]; then
        # Log outdated packages
        if [ -n "$OUTDATED" ]; then
            while read -r line; do
                PKG=$(echo "$line" | cut -d= -f1)
                NEW_VER=$(echo "$line" | cut -d= -f3)
                OLD_VER="${INSTALLED_PACKAGES[$PKG]}"
                echo "$LOG_PREFIX Updating package: $PKG $OLD_VER → $NEW_VER"
            done <<< "$OUTDATED"
        fi

        # Log missing packages
        if [ -n "$MISSING" ]; then
            while read -r pkg; do
                VER=$(grep -i "^$pkg==" "$REQ_FILE_PATH" | cut -d= -f3)
                echo "$LOG_PREFIX Installing new package: $pkg $VER"
            done <<< "$MISSING"
        fi

        # Install/Update packages, suppress "Requirement already satisfied"
        $PIP_BIN install --upgrade --disable-pip-version-check -q -q -r "$REQ_FILE_PATH" >/dev/null || { echo "$LOG_PREFIX ERROR: pip install failed."; exit 1; }

        echo "$LOG_PREFIX Dependencies installed/updated successfully."
    else
        echo "$LOG_PREFIX All dependencies are already up to date."
    fi
else
    echo "$LOG_PREFIX requirements.txt not found. Skipping pip install."
fi

# 5. Run tubesync-plex
if [ -f "$BASE_DIR/tubesync-plex-metadata.py" ]; then
    echo "$LOG_PREFIX Running tubesync-plex with config $CONFIG_FILE..."
    "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE" || { echo "$LOG_PREFIX ERROR: tubesync-plex-metadata.py execution failed."; exit 1; }
else
    echo "$LOG_PREFIX ERROR: tubesync-plex-metadata.py not found in $BASE_DIR."
    exit 1
fi

echo "$LOG_PREFIX END"
