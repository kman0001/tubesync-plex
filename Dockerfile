# syntax=docker/dockerfile:1.4

# ================================
# Stage 1: Builder (for venv & dependencies)
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

# Install build dependencies for C extensions
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

# Create virtual environment and install dependencies
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# ================================
# Stage 2: Runtime (slim)
# ================================
FROM python:3.11-slim

# Install only runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /app/venv ./venv

# Copy app code and entrypoint
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
