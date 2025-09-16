# syntax=docker/dockerfile:1.4

# ================================
# Stage 1: Builder
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

# Install build dependencies (required for psutil and other C extensions)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libffi-dev \
        make \
        git \
        curl \
        bash \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python requirements
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# ================================
# Stage 2: Final image
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim

# Install only runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        inotify-tools \
        git \
        curl \
        bash \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /app/venv ./venv

# Copy application files
COPY tubesync-plex-metadata.py . 
COPY entrypoint/ ./entrypoint/

# Make entrypoint scripts executable
RUN chmod +x /app/entrypoint/*.sh

# Set entrypoint
ENTRYPOINT ["/app/entrypoint/entrypoint.sh"]
