# syntax=docker/dockerfile:1.4

# ================================
# Base image
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime + build dependencies (for venv and C extensions like psutil)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libffi-dev \
        make \
        bash \
    && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .

# Create virtual environment and install Python dependencies
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
