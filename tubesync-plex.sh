#!/bin/bash
set -e

# ----------------------------
# Helper function
# ----------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# Parse arguments
# ----------------------------
BASE_DIR=""
DISABLE_WATCHDOG=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --disable-watchdog) DISABLE_WATCHDOG=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$BASE_DIR" ]; then
    echo "ERROR: --base-dir must be specified"
    exit 1
fi

REPO_URL="https://github.com/kman0001/tubesync-plex.git"
mkdir -p "$BASE_DIR"
PIP_BIN="$BASE_DIR/venv/bin/pip"
PY_FILE="$BASE_DIR/tubesync-plex-metadata.py"
REQ_FILE="$BASE_DIR/requirements.txt"
FFMPEG_BIN="$BASE_DIR/venv/bin/ffmpeg"
FFMPEG_CHECKSUM_FILE="$BASE_DIR/venv/bin/.ffmpeg_checksum"

# ----------------------------
# 1. Git fetch + reset
# ----------------------------
cd "$BASE_DIR"
if [ ! -d "$BASE_DIR/.git" ]; then
    log "Initializing git repository..."
    git init
    git remote add origin "$REPO_URL"
    git fetch origin
    git reset --hard origin/main
else
    log "Updating repository..."
    git fetch origin
    git reset --hard origin/main
fi

# ----------------------------
# 2. Python venv
# ----------------------------
if [ ! -d "$BASE_DIR/venv" ]; then
    log "Creating virtual environment..."
    python3 -m venv "$BASE_DIR/venv"
else
    log "Virtual environment already exists."
fi

# ----------------------------
# 3. Install / update Python dependencies
# ----------------------------
log "Installing/updating Python dependencies..."
if [ -f "$REQ_FILE" ]; then
    "$PIP_BIN" install --disable-pip-version-check -q -r "$REQ_FILE"
fi

# ----------------------------
# 4. Setup static FFmpeg in venv (with architecture detection & checksum)
# ----------------------------
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
    FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
elif [ "$ARCH" = "aarch64" ]; then
    FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
else
    log "Unsupported architecture: $ARCH"
    exit 1
fi

# Calculate remote file checksum (sha256)
REMOTE_SHA=$(curl -sL "$FFMPEG_URL.sha256" | awk '{print $1}')
LOCAL_SHA=""
if [ -f "$FFMPEG_CHECKSUM_FILE" ]; then
    LOCAL_SHA=$(cat "$FFMPEG_CHECKSUM_FILE")
fi

if [ ! -x "$FFMPEG_BIN" ] || [ "$REMOTE_SHA" != "$LOCAL_SHA" ]; then
    log "Downloading/updating static FFmpeg..."
    mkdir -p "$BASE_DIR/venv/bin"
    curl -L "$FFMPEG_URL" | tar -xJ --strip-components=1 -C "$BASE_DIR/venv/bin" ffmpeg
    chmod +x "$FFMPEG_BIN"
    echo "$REMOTE_SHA" > "$FFMPEG_CHECKSUM_FILE"
else
    log "Static FFmpeg is up-to-date."
fi

# Add venv bin to PATH so Python subprocess uses this FFmpeg
export PATH="$BASE_DIR/venv/bin:$PATH"

# ----------------------------
# 5. Run Python script
# ----------------------------
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    CMD="$BASE_DIR/venv/bin/python $PY_FILE --config $BASE_DIR/config/config.json"
    if [ "$DISABLE_WATCHDOG" = true ]; then
        CMD="$CMD --disable-watchdog"
    fi
    exec $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi
