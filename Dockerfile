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

# 코드 복사 (venv는 제외)
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY config.json .
COPY entrypoint/ /app/entrypoint/

# Python 가상환경 생성
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install --upgrade -r requirements.txt

# 엔트리포인트 실행
ENTRYPOINT ["/app/entrypoint/entrypoint_nfo_watch.sh"]
