# 베이스 이미지
FROM python:3.11-slim

# 환경 설정
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        inotify-tools \
        git \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 소스 코드 복사
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY entrypoint/ /app/entrypoint/

# Python 가상환경 생성
RUN python -m venv /app/venv

# 패키지 설치
RUN /app/venv/bin/pip install --upgrade pip
RUN /app/venv/bin/pip install --upgrade -r requirements.txt

# 엔트리포인트
ENTRYPOINT ["/bin/sh", "-c", "/app/entrypoint/entrypoint_nfo_watch.sh --base-dir /app --watch-dir /downloads"]
