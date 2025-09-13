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
        if ! git clone "$REPO_URL" "$BASE_DIR"; then
            echo "$LOG_PREFIX ERROR: Failed to clone repository."
            exit 1
        fi
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
        if ! git merge --no-edit origin/$BRANCH; then
            echo "$LOG_PREFIX Merge conflict detected. Overwriting with remote version..."
            git reset --hard origin/$BRANCH || { echo "$LOG_PREFIX ERROR: git reset failed."; popd >/dev/null; exit 1; }
        fi
    else
        echo "$LOG_PREFIX No updates from GitHub."
    fi
    popd >/dev/null
fi

# 2. Check if python3-venv is installed
if ! dpkg -s python3-venv &>/dev/null; then
    if [ "$(id -u)" -ne 0 ]; then
        echo "$LOG_PREFIX ERROR: You need root privileges to install python3-venv."
        exit 1
    fi
    echo "$LOG_PREFIX Installing python3-venv..."
    apt update && apt install -y python3-venv || { echo "$LOG_PREFIX ERROR: Failed to install python3-venv."; exit 1; }
else
    echo "$LOG_PREFIX python3-venv is already installed."
fi

# 3. Create virtual environment if it does not exist
if [ ! -d "$BASE_DIR/venv" ]; then
    echo "$LOG_PREFIX Creating virtual environment..."
    if ! python3 -m venv "$BASE_DIR/venv"; then
        echo "$LOG_PREFIX ERROR: Failed to create virtual environment."
        exit 1
    fi
else
    echo "$LOG_PREFIX Virtual environment already exists."
fi

# 4. Install or update Python dependencies only if needed
if [ -f "$BASE_DIR/requirements.txt" ]; then
    echo "$LOG_PREFIX Checking Python dependencies..."

    PIP_BIN="$BASE_DIR/venv/bin/pip"

    # 현재 설치된 패키지
    INSTALLED_PACKAGES=$($PIP_BIN freeze)

    # 설치해야 할 패키지 (아직 설치되지 않은 것만)
    MISSING_PACKAGES=$(grep -v '^#' "$BASE_DIR/requirements.txt" | while read -r pkg; do
        echo "$INSTALLED_PACKAGES" | grep -i -q "^$pkg" || echo "$pkg"
    done)

    # 업데이트 필요한 패키지
    OUTDATED_PACKAGES=$($PIP_BIN list --outdated --format=freeze | cut -d= -f1)

    if [ -n "$MISSING_PACKAGES" ] || [ -n "$OUTDATED_PACKAGES" ]; then
        echo "$LOG_PREFIX Installing/Updating Python dependencies..."
        # requirements.txt 기반 설치 (설치 또는 업데이트 발생)
        if ! $PIP_BIN install --upgrade --disable-pip-version-check -q -q -r "$BASE_DIR/requirements.txt"; then
            echo "$LOG_PREFIX ERROR: pip install failed."
            exit 1
        fi
    else
        echo "$LOG_PREFIX All dependencies are already up to date."
    fi
else
    echo "$LOG_PREFIX requirements.txt not found. Skipping pip install."
fi


# 5. Run tubesync-plex with the JSON configuration
if [ -f "$BASE_DIR/tubesync-plex-metadata.py" ]; then
    echo "$LOG_PREFIX Running tubesync-plex with config $CONFIG_FILE..."
    if ! "$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --config "$CONFIG_FILE"; then
        echo "$LOG_PREFIX ERROR: tubesync-plex-metadata.py execution failed."
        exit 1
    fi
else
    echo "$LOG_PREFIX ERROR: tubesync-plex-metadata.py not found in $BASE_DIR."
    exit 1
fi

echo "$LOG_PREFIX END"
