#!/bin/bash
set -e

# ----------------------------
# Helper function
# ----------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

# ----------------------------
# 0. Detect OS
# ----------------------------
OS_TYPE=""
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_TYPE=$ID
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS_TYPE="macos"
elif [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* ]]; then
    OS_TYPE="windows"
else
    OS_TYPE="unknown"
fi

# ----------------------------
# 1. Check required system packages
# ----------------------------
REQUIRED_PACKAGES=(git python3 pip3)
MISSING_PACKAGES=()

for PKG in "${REQUIRED_PACKAGES[@]}"; do
    if ! command -v "$PKG" &>/dev/null; then
        MISSING_PACKAGES+=("$PKG")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    log "ERROR: Missing required system packages: ${MISSING_PACKAGES[*]}"
    case $OS_TYPE in
        ubuntu|debian)
            log "Install with: sudo apt update && sudo apt install -y ${MISSING_PACKAGES[*]}"
            ;;
        centos|rhel|fedora)
            log "Install with: sudo yum install -y ${MISSING_PACKAGES[*]}"
            ;;
        arch)
            log "Install with: sudo pacman -Syu ${MISSING_PACKAGES[*]}"
            ;;
        macos)
            log "Install with Homebrew: brew install ${MISSING_PACKAGES[*]}"
            ;;
        windows)
            log "Please install these packages manually or via Chocolatey: choco install ${MISSING_PACKAGES[*]}"
            ;;
        *)
            log "Unknown OS. Please install packages manually: ${MISSING_PACKAGES[*]}"
            ;;
    esac
    exit 1
else
    log "All required system packages are installed."
fi

# ----------------------------
# 2. Parse arguments
# ----------------------------
BASE_DIR=""
EXTRA_PY_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        --disable-watchdog|--debug-http|--debug|--detail) 
            EXTRA_PY_ARGS+=("$1")
            shift ;;
        *)
            log "Unknown option: $1"
            exit 1 ;;
    esac
done

# ----------------------------
# 3. Set default BASE_DIR if not specified
# ----------------------------
if [ -n "$BASE_DIR" ]; then
    mkdir -p "$BASE_DIR"
fi

PY_FILE="${BASE_DIR:-/app}/tubesync-plex-metadata.py"
REQ_FILE="${BASE_DIR:-/app}/requirements.txt"
VENV_DIR="${BASE_DIR:-/app}/venv"
PIP_BIN="$VENV_DIR/bin/pip"
REPO_URL="https://github.com/kman0001/tubesync-plex.git"

# ----------------------------
# 4. Git clone or fetch/reset
# ----------------------------
if [ ! -d "${BASE_DIR:-/app}/.git" ]; then
    log "Cloning repository..."
    git clone "$REPO_URL" "${BASE_DIR:-/app}"
else
    log "Updating repository..."
    cd "${BASE_DIR:-/app}"
    git fetch origin
    git reset --hard origin/main
fi

# ----------------------------
# 5. Python venv
# ----------------------------
if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment..."
    if python3 -m venv "$VENV_DIR" 2>/dev/null; then
        log "Python venv created successfully."
    else
        log "Python venv module not available, trying virtualenv..."
        if ! command -v virtualenv &>/dev/null; then
            log "ERROR: virtualenv not found. Please install it using 'pip install --user virtualenv'."
            exit 1
        fi
        virtualenv "$VENV_DIR"
        log "Virtual environment created via virtualenv."
    fi
else
    log "Virtual environment already exists."
fi

# ----------------------------
# 6. Install / update Python dependencies
# ----------------------------
log "Installing/updating Python dependencies..."
if [ -f "$REQ_FILE" ]; then
    "$PIP_BIN" install --disable-pip-version-check -q -r "$REQ_FILE"
fi
export PATH="$VENV_DIR/bin:$PATH"

# ----------------------------
# 7. Run Python script
# ----------------------------
if [ -f "$PY_FILE" ]; then
    log "Running tubesync-plex..."
    # BASE_DIR 환경 변수 전달
    export BASE_DIR="${BASE_DIR:-/app}"
    CMD="python3 $PY_FILE --config $BASE_DIR/config/config.json ${EXTRA_PY_ARGS[*]}"
    exec $CMD
else
    log "ERROR: tubesync-plex-metadata.py not found."
    exit 1
fi

