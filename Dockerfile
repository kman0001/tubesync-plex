# syntax=docker/dockerfile:1.4
# python:3.11-slim base

# ================================
# Stage 1: Builder
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .

# Install build dependencies (required for lxml, psutil, watchdog)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
        libxml2-dev \
        libxslt1-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip + install Python dependencies without cache and disable version check
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --disable-pip-version-check -r requirements.txt


# ================================
# Stage 2: Runtime
# ================================
FROM python:3.11-slim
WORKDIR /app

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash \
        libxml2 \
        libxslt1.1 \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# Download and install static ffmpeg according to the target platform
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

# Copy Python packages installed in the builder stage
COPY --from=builder /usr/local /usr/local

# Copy application source code and entrypoint script
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
