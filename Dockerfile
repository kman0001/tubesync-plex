FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        inotify-tools \
        git \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY config.json .
COPY entrypoint/ /app/entrypoint/

# Python venv and dependencies
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip setuptools wheel && \
    /app/venv/bin/pip install --upgrade -r requirements.txt

# Entrypoint
ENTRYPOINT ["/bin/bash", "/app/entrypoint/entrypoint_nfo_watch.sh"]

# Default CMD
CMD ["--base-dir", "/app", "--watch-dir", "/downloads"]
