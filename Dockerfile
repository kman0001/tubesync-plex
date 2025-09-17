# syntax=docker/dockerfile:1.4

# ================================
# Stage 1: Builder (for venv & Python deps)
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libffi-dev \
        make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Create virtual environment and install Python deps
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# ================================
# Stage 2: Runtime
# ================================
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends bash curl xz-utils && \
    rm -rf /var/lib/apt/lists/*

# Detect platform and download static ffmpeg
ARG TARGETPLATFORM
RUN TMPDIR=$(mktemp -d) && \
    if [ "$TARGETPLATFORM" = "linux/amd64" ]; then \
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"; \
    elif [ "$TARGETPLATFORM" = "linux/arm64" ]; then \
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"; \
    else \
        echo "Unsupported platform: $TARGETPLATFORM" && exit 1; \
    fi && \
    curl -L $FFMPEG_URL | tar -xJ -C $TMPDIR && \
    cp $TMPDIR/ffmpeg*/ffmpeg /usr/local/bin/ && \
    chmod +x /usr/local/bin/ffmpeg && \
    rm -rf $TMPDIR

# Copy venv from builder
COPY --from=builder /app/venv ./venv

# Copy app code and entrypoint
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
