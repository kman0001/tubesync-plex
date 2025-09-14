# 베이스 이미지
FROM python:3.11-slim

# 작업 디렉토리
WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends inotify-tools && \
    rm -rf /var/lib/apt/lists/*

# 애플리케이션 파일 복사
COPY requirements.txt .
COPY tubesync-plex-metadata.py .
COPY entrypoint/ /app/entrypoint/

# Python 가상환경 생성
RUN python -m venv venv

# 가상환경 활성화 후 의존성 설치
RUN /bin/sh -c "venv/bin/pip install --upgrade pip && \
    [ -f requirements.txt ] && venv/bin/pip install -r requirements.txt || true"

# 엔트리포인트
ENTRYPOINT ["/bin/sh", "/app/entrypoint/entrypoint.sh"]
