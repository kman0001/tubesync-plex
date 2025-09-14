FROM python:3.11-slim

# 필수 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    inotify-tools \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# 코드 복사
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY entrypoint/ /app/entrypoint/

# Python 가상환경
RUN python -m venv venv \
    && ./venv/bin/pip install --upgrade pip \
    && ./venv/bin/pip install -r requirements.txt

# 엔트리포인트 실행 권한
RUN chmod +x /app/entrypoint/entrypoint.sh
RUN chmod +x /app/entrypoint/entrypoint_nfo_watch.sh

ENTRYPOINT ["/app/entrypoint/entrypoint.sh"]
