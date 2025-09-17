# syntax=docker/dockerfile:1.4
# python:3.11-alpine base

# ================================
# Stage 1: Builder (install deps)
# ================================
FROM --platform=$BUILDPLATFORM python:3.11-alpine AS builder

# 빌드용 deps 설치 (lxml, psutil, watchdog 빌드용)
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

# pip 최신화 + 캐시 없이 설치 + 버전 체크 비활성화
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --disable-pip-version-check -r requirements.txt


# ================================
# Stage 2: Runtime
# ================================
FROM python:3.11-alpine
WORKDIR /app

# 런타임 의존성 설치 (최소)
RUN apk add --no-cache \
    bash \
    curl \
    xz \
    libxml2 \
    libxslt \
    libstdc++

# ffmpeg 다운로드 및 설치 (플랫폼별)
ARG TARGETPLATFORM
RUN TMPDIR=$(mktemp -d) && \
    if [ "$TARGETPLATFORM" = "linux/amd64" ]; then \
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"; \
    elif [ "$TARGETPLATFORM" = "linux/arm64" ]; then \
        FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"; \
    else \
        echo "Unsupported platform: $TARGETPLATFORM" && exit 1; \
    fi && \
    curl -L $FFMPEG_URL | tar -xJ -C $TMPDIR && \
    cp $TMPDIR/ffmpeg*/ffmpeg /usr/local/bin/ && \
    chmod +x /usr/local/bin/ffmpeg && \
    rm -rf $TMPDIR

# builder stage에서 설치한 Python 패키지만 runtime으로 복사
COPY --from=builder /usr/local /usr/local

# 앱 소스 및 엔트리포인트 복사
COPY tubesync-plex-metadata.py .
COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
