# syntax=docker/dockerfile:1.7

# ==========================================
# Stage 1: Builder
# ==========================================
FROM --platform=$BUILDPLATFORM python:3.11-alpine AS builder

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

RUN python -m venv /app/venv && \
    /app/venv/bin/pip install \
        --upgrade \
        pip \
        setuptools \
        wheel \
        --no-cache-dir && \
    /app/venv/bin/pip install \
        --no-cache-dir \
        --prefer-binary \
        -r requirements.txt


# ==========================================
# Stage 2: Runtime
# ==========================================
FROM python:3.11-alpine

WORKDIR /app

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PATH="/app/venv/bin:$PATH"

# Runtime dependencies
RUN apk add --no-cache \
    bash \
    libxml2 \
    libxslt \
    libstdc++

# Python virtual environment
COPY --from=builder /app/venv /app/venv

# Application
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .

# ==========================================
# FFmpeg
# ==========================================
ARG TARGETARCH

COPY ffmpeg/${TARGETARCH}/ffmpeg /usr/local/bin/ffmpeg
COPY ffmpeg/${TARGETARCH}/ffprobe /usr/local/bin/ffprobe

RUN chmod +x \
    /app/entrypoint.sh \
    /usr/local/bin/ffmpeg \
    /usr/local/bin/ffprobe

# ==========================================
# Verify architecture-specific binaries
# ==========================================
RUN /usr/local/bin/ffmpeg -version | head -n 1 && \
    /usr/local/bin/ffprobe -version | head -n 1

ENTRYPOINT ["/app/entrypoint.sh"]
