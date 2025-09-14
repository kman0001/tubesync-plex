FROM python:3.11-slim

# s6 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    inotify-tools curl git s6 && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리
WORKDIR /app

# entrypoint 복사
COPY entrypoint/tubesync-plex /app/entrypoint/tubesync-plex
COPY config /app/config

# s6 서비스 폴더 복사
COPY services.d /app/services.d

# 권한
RUN chmod -R +x /app/entrypoint/tubesync-plex \
    && chmod -R +x /app/services.d

# s6가 PID 1로 실행되도록
ENTRYPOINT ["/bin/s6-svscan", "/app/services.d"]
