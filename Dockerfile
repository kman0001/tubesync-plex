FROM python:3.11-slim

# 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends inotify-tools curl git s6 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 요구사항 및 코드 복사
COPY requirements.txt .
COPY entrypoint/ /app/entrypoint/

# Python 가상환경 생성 및 패키지 설치
RUN python -m venv /app/entrypoint/venv && \
    /app/entrypoint/venv/bin/pip install --upgrade pip && \
    /app/entrypoint/venv/bin/pip install -r requirements.txt

# s6 서비스 폴더 복사
COPY services.d/ /etc/services.d/

# s6-init 실행
ENTRYPOINT ["/init"]
