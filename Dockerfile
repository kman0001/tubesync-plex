# 베이스 이미지
FROM python:3.11-slim

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        inotify-tools \
        git \
        curl \
        bash \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# 필요한 파일 복사
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY entrypoint/entrypoint_nfo_watch.sh /app/entrypoint/entrypoint_nfo_watch.sh
COPY entrypoint/entrypoint.sh /app/entrypoint/entrypoint.sh

# 파이썬 가상환경 생성 및 패키지 설치
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip setuptools wheel && \
    /app/venv/bin/pip install -r requirements.txt

# 엔트리포인트 스크립트 권한
RUN chmod +x /app/entrypoint/entrypoint_nfo_watch.sh \
    && chmod +x /app/entrypoint/entrypoint.sh

# 환경변수 기본값
ENV BASE_DIR=/app \
    WATCH_DIR=/downloads \
    CONFIG_FILE=/app/config/config.json

# 엔트리포인트
ENTRYPOINT ["/app/entrypoint/entrypoint_nfo_watch.sh"]
