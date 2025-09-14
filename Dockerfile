FROM python:3.11-slim

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends inotify-tools curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 필요 파일 복사
COPY entrypoint/tubesync-plex /app/entrypoint/tubesync-plex

# 가상환경 준비
RUN python -m venv /app/entrypoint/tubesync-plex/venv

# s6 설치 (간단 예시)
RUN apt-get update && \
    apt-get install -y --no-install-recommends s6 && \
    rm -rf /var/lib/apt/lists/*

# s6 초기화 스크립트 복사
COPY s6/ /etc/services.d/
