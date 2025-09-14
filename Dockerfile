# 베이스 이미지
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        inotify-tools \
        git \
        curl \
        && rm -rf /var/lib/apt/lists/*

# 의존성 파일 복사
COPY requirements.txt .
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# tubesync-plex 스크립트 및 entrypoint 복사
COPY tubesync-plex-metadata.py .
COPY entrypoint/ /app/entrypoint/tubesync-plex/
RUN chmod +x /app/entrypoint/tubesync-plex/*.sh

# Config 파일 경로 (컨테이너 안)
VOLUME ["/app/config"]

# 엔트리포인트 지정
ENTRYPOINT ["/app/entrypoint/tubesync-plex/entrypoint_nfo_watch.sh"]
