# syntax=docker/dockerfile:1.4

# ================================
# Stage 1: Builder (for C extensions)
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies (required for psutil)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libffi-dev \
        make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Create virtual environment and install Python dependencies
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# ================================
# Stage 2: Final image (runtime)
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim

WORKDIR /app

# Install only runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /app/venv ./venv

# Copy application files
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
