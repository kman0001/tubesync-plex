# 베이스 이미지
FROM python:3.11-slim

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends inotify-tools git curl && \
    rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# Python 요구사항과 스크립트 복사
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY entrypoint/ /app/entrypoint/

# Python 가상환경 생성 및 패키지 설치
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install -r requirements.txt

# 엔트리포인트 스크립트 권한
RUN chmod +x /app/entrypoint/entrypoint_nfo_watch.sh

# 외부 config.json 마운트 경로
VOLUME ["/app/config", "/downloads"]

# 엔트리포인트 실행
ENTRYPOINT ["/app/entrypoint/entrypoint_nfo_watch.sh"]
