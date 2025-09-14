# 베이스 이미지
FROM python:3.11-slim

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        inotify-tools \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# Python requirements, metadata 스크립트, 엔트리포인트 복사
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY entrypoint/entrypoint.sh /app/entrypoint/entrypoint.sh
COPY entrypoint/entrypoint_nfo_watch.sh /app/entrypoint/entrypoint_nfo_watch.sh

# 가상환경 생성 및 패키지 설치
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install --no-cache-dir -r requirements.txt

# 실행 권한 부여
RUN chmod +x /app/entrypoint/entrypoint.sh /app/entrypoint/entrypoint_nfo_watch.sh

# 엔트리포인트
ENTRYPOINT ["/app/entrypoint/entrypoint.sh"]
