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

# Python 의존성 복사
COPY requirements.txt .
RUN python -m venv venv
RUN ./venv/bin/pip install --upgrade pip
RUN ./venv/bin/pip install -r requirements.txt

# 앱 파일 복사
COPY tubesync-plex-metadata.py .

# 엔트리포인트 스크립트 복사
COPY entrypoint/entrypoint.sh /app/entrypoint/entrypoint.sh
COPY entrypoint/entrypoint_nfo_watch.sh /app/entrypoint/entrypoint_nfo_watch.sh

# 실행 권한
RUN chmod +x /app/entrypoint/entrypoint.sh
RUN chmod +x /app/entrypoint/entrypoint_nfo_watch.sh

# 엔트리포인트 지정
ENTRYPOINT ["/app/entrypoint/entrypoint.sh"]
