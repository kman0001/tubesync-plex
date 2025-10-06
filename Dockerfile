# syntax=docker/dockerfile:1.4
# python:3.11-alpine base

# ================================
# Stage 1: Builder (install deps)
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-alpine AS builder

# Install build dependencies (for lxml, psutil, watchdog)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    make

WORKDIR /app
COPY requirements.txt .

# Create Python virtual environment and install packages
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip setuptools wheel --no-cache-dir && \
    /app/venv/bin/pip install --no-cache-dir --prefer-binary -r requirements.txt

# ================================
# Stage 2: Runtime
# ================================
FROM python:3.11-alpine
WORKDIR /app

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PATH="/app/venv/bin:$PATH"

# Install minimal runtime dependencies
RUN apk add --no-cache \
    bash \
    libxml2 \
    libxslt \
    libstdc++

# Copy only the virtual environment from the builder stage
COPY --from=builder /app/venv /app/venv

# Copy application source and entrypoint
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

# Set the container entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
