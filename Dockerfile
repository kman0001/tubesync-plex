# syntax=docker/dockerfile:1.4

FROM python:3.11-slim

# ================================
# Set working directory
# ================================
WORKDIR /app

# ================================
# Install minimal OS packages
# Bash is required for entrypoint scripts
# ================================
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
    && rm -rf /var/lib/apt/lists/*

# ================================
# Install Python dependencies
# ================================
COPY requirements.txt .
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --disable-pip-version-check -r requirements.txt

# ================================
# Copy application files and entrypoint scripts
# ================================
COPY tubesync-plex-metadata.py .
COPY entrypoint/ ./entrypoint/
RUN chmod +x ./entrypoint/*.sh

# ================================
# Set default environment variables
# ================================
ENV BASE_DIR=/app
ENV CONFIG_FILE=/app/config/config.json
ENV DEBOUNCE_DELAY=2

# ================================
# Execute entrypoint script on container start
# ================================
ENTRYPOINT ["/app/entrypoint/entrypoint.sh"]
