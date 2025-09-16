# syntax=docker/dockerfile:1.4

# ================================
# Base image (multi-arch build supported)
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim AS base

# ================================
# Install system dependencies
# ================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl \
        bash \
        inotify-tools \
        libffi-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# ================================
# Working directory
# ================================
WORKDIR /app

# ================================
# Copy requirements first (cache efficiency)
# ================================
COPY requirements.txt .

# ================================
# Create virtual environment and install dependencies
# ================================
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# ================================
# Copy app files and entrypoint scripts
# ================================
COPY tubesync-plex-metadata.py .
COPY entrypoint/ ./entrypoint/

# Give execute permission to entrypoint scripts
RUN chmod +x ./entrypoint/*.sh

# ================================
# Default environment variables
# ================================
ENV BASE_DIR=/app
ENV CONFIG_FILE=/app/config/config.json
ENV DEBOUNCE_DELAY=2

# ================================
# Entrypoint
# ================================
ENTRYPOINT ["/app/entrypoint/entrypoint.sh"]
