#!/bin/bash
set -e

# ----------------------------
# Helper function
# ----------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# 0. Install required system packages (multi-distro)
# ----------------------------
REQUIRED_PACKAGES=(git python3 python3-venv curl tar xz)
MISSING_PACKAGES=()

for PKG in "${REQUIRED_PACKAGES[@]}"; do
    if ! command -v "$PKG" &>/dev/null; then
        MISSING_PACKAGES+=("$PKG")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    log "Missing packages: ${MISSING_PACKAGES[*]}"
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        PKG_MANAGER=""
        UPDATE_CMD=""
        INSTALL_CMD=""
        case "$ID" in
            debian|ubuntu)
                PKG_MANAGER="apt-get"
                UPDATE_CMD="sudo apt-get update -qq"
                INSTALL_CMD="sudo apt-get install -y"
                ;;
            fedora)
                PKG_MANAGER="dnf"
                UPDATE_CMD="sudo dnf makecache -q"
                INSTALL_CMD="sudo dnf install -y"
                ;;
            centos|rhel)
                if command -v dnf &>/dev/null; then
                    PKG_MANAGER="dnf"
                    UPDATE_CMD="sudo dnf makecache -q"
                    INSTALL_CMD="sudo dnf install -y"
                else
                    PKG_MANAGER="yum"
                    UPDATE_CMD="sudo yum makecache -q"
                    INSTALL_CMD="sudo yum install -y"
                fi
                ;;
            alpine)
                PKG_MANAGER="apk"
                UPDATE_CMD="sudo apk update"
                INSTALL_CMD="sudo apk add"
                ;;
            arch|manjaro)
                PKG_MANAGER="pacman"
                UPDATE_CMD="sudo pacman -Sy --noconfirm"
                INSTALL_CMD="sudo pacman -S --noconfirm"
                ;;
        esac

        if [ -n "$PKG_MANAGER" ]; then
            log "Detected OS: $ID → Using $PKG_MANAGER"
            log "Updating package index..."
            eval "$UPDATE_CMD"
            log "Installing missing packages..."
            eval "$INSTALL_CMD ${MISSING_PACKAGES[*]}"
        else
            log "WARNING: Unsupported OS detected ($ID)."
            log "Please manually install: ${MISSING_PACKAGES[*]}"
            exit 1
        fi
    else
        log "Cannot detect OS. Please manually install: ${MISSING_PACKAGES[*]}"
        exit 1
    fi
else
    log "All required packages are installed."
fi

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
FFPROBE_BIN="$BASE_DIR/venv/bin/ffprobe"
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

REMOTE_SHA=$(curl -sL "$FFMPEG_URL.sha256" | awk '{print $1}')
LOCAL_SHA=""
if [ -f "$FFMPEG_CHECKSUM_FILE" ]; then
    LOCAL_SHA=$(cat "$FFMPEG_CHECKSUM_FILE")
fi

if [ ! -x "$FFMPEG_BIN" ] || [ "$REMOTE_SHA" != "$LOCAL_SHA" ]; then
    log "Downloading/updating static FFmpeg..."
    TMP_DIR=$(mktemp -d)
    mkdir -p "$BASE_DIR/venv/bin"

    curl --progress-bar -L "$FFMPEG_URL" | tar -xJ -C "$TMP_DIR"

    FFMPEG_PATH=$(find "$TMP_DIR" -type f -name "ffmpeg" | head -n 1)
    FFPROBE_PATH=$(find "$TMP_DIR" -type f -name "ffprobe" | head -n 1)
    if [ -z "$FFMPEG_PATH" ]; then
        log "ERROR: ffmpeg binary not found in downloaded archive."
        rm -rf "$TMP_DIR"
        exit 1
    fi
    cp "$FFMPEG_PATH" "$FFMPEG_BIN"
    chmod +x "$FFMPEG_BIN"

    if [ -n "$FFPROBE_PATH" ]; then
        cp "$FFPROBE_PATH" "$FFPROBE_BIN"
        chmod +x "$FFPROBE_BIN"
    fi

    echo "$REMOTE_SHA" > "$FFMPEG_CHECKSUM_FILE"
    rm -rf "$TMP_DIR"
else
    log "Static FFmpeg is up-to-date."
fi

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
