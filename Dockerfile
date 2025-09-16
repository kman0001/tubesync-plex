# syntax=docker/dockerfile:1.4
FROM --platform=$BUILDPLATFORM python:3.11-slim

WORKDIR /app

# Install runtime + build dependencies for venv
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc python3-dev libffi-dev make bash \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and app
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .

# Create venv and install dependencies (runtime stage)
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
