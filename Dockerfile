# syntax=docker/dockerfile:1.4

# 베이스 이미지 (buildx 아키텍처 지원)
FROM --platform=$BUILDPLATFORM python:3.11-slim AS base

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

# Python 의존성 복사 및 가상환경 생성
COPY requirements.txt .
RUN python -m venv venv && \
    ./venv/bin/pip install --upgrade pip && \
    ./venv/bin/pip install -r requirements.txt

# 앱 파일 복사
COPY tubesync-plex-metadata.py .

# 엔트리포인트 스크립트 복사
COPY entrypoint/ /app/entrypoint/

# 실행 권한 부여
RUN chmod +x /app/entrypoint/*.sh

# 엔트리포인트 지정
ENTRYPOINT ["/app/entrypoint/entrypoint.sh"]
