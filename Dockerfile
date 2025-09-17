# syntax=docker/dockerfile:1.4

# ================================
# Stage 1: Builder (Python venv & deps)
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

# Install build dependencies for Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libffi-dev \
        make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# ================================
# Stage 2: Runtime
# ================================
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies and download FFmpeg
ARG TARGETPLATFORM
RUN apt-get update && \
    apt-get install -y --no-install-recommends bash curl xz-utils && \
    if [ "$TARGETPLATFORM" = "linux/amd64" ]; then \
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"; \
    elif [ "$TARGETPLATFORM" = "linux/arm64" ]; then \
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"; \
    else \
        echo "Unsupported platform: $TARGETPLATFORM" && exit 1; \
    fi && \
    curl -L $FFMPEG_URL | tar -xJ --strip-components=1 -C /usr/local/bin ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /app/venv ./venv

# Copy application code and entrypoint
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
