# TubeSync Plex Metadata Sync (Personal Update)

This repository is a **personal fork** of [tgouverneur/tubesync-plex](https://github.com/tgouverneur/tubesync-plex) and has been updated for **personal use**.

## Key Changes in this Fork
- Simplified default log output
- Added `-d / --detail` option for detailed metadata updates
- Disallow simultaneous use of `-s / --silent` and `-d / --detail` options

> ⚠️ **Note:** This fork is maintained for personal purposes and may differ from the original repository.



---
---


# TubeSync Plex Metadata Sync Tool

This tool syncs metadata from `.nfo` files to your Plex library. It reads metadata from NFO files associated with video files in your Plex library and updates the corresponding Plex items. After a successful update, the NFO file is deleted.

## Features

* Supports common video formats: `.mkv`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.flv`, `.m4v`.
* Reads metadata from NFO files and updates Plex title, aired date, and plot.
* Deletes NFO files after successful metadata sync.
* Supports multiple Plex libraries.
* Optional detailed logs (`--detail`).
* Optional subtitle uploads (`--subtitles`).

## Requirements

* Python 3.10+
* Plex server and API token
* `pip` dependencies (installed automatically by `tubesync-plex.sh`)

## Installation & Usage

### 1. Clone or update repository

You can use the provided `tubesync-plex.sh` script:

```bash
chmod +x tubesync-plex.sh
./tubesync-plex.sh
```

* The script will clone the repository if it does not exist, or pull updates if it does.
* Python virtual environment (`venv`) will be created automatically.
* Python dependencies will be installed automatically.

### 2. Configure

The script uses `config.json` for configuration. On first run, it will create a default `config.json` in the current folder:

```json
{
    "_comment": {
        "plex_base_url": "Your Plex server base URL, e.g., http://localhost:32400",
        "plex_token": "Your Plex server token",
        "plex_library_names": ["Library1", "Library2"],
        "silent": "true or false, suppress log output",
        "detail": "true or false, show detailed logs",
        "subtitles": "true or false, upload subtitles if available"
    },
    "plex_base_url": "",
    "plex_token": "",
    "plex_library_names": ["YourLibraryName"],
    "silent": false,
    "detail": false,
    "subtitles": false
}
```

Edit `config.json` with your Plex information and desired settings before rerunning the script.

### 3. Run manually

```bash
./tubesync-plex.sh
```

### 4. Cron job (optional)

To run periodically, add a cron job:

```bash
# Edit crontab
crontab -e

# Example: run daily at 3 AM
0 3 * * * /path/to/tubesync-plex.sh >> /path/to/tubesync.log 2>&1
```

## Notes

* The script references Plex libraries; the user running the script must have access to Plex library folders.
* NFO files are deleted **only after successful metadata updates**.
* Detailed logs are shown if `detail` is `true`.
* Silent mode suppresses most log outputs if `silent` is `true`.




---

# TubeSync Plex Metadata Sync Tool

## 소개

TubeSync Plex Metadata Sync Tool은 Plex 라이브러리의 에피소드 메타데이터를 TubeSync에서 가져온 NFO 파일을 기준으로 업데이트합니다. 또한, NFO 파일을 적용 후 삭제하여 라이브러리를 깔끔하게 유지할 수 있습니다.

---

## 요구 사항

* Python 3.10 이상
* plexapi
* lxml
* requests

설치는 `tubesync-plex.sh` 실행 시 자동으로 이루어집니다.

---

## 설치 및 실행

1. GitHub 저장소 클론 또는 업데이트:

```bash
./tubesync-plex.sh
```

2. 가상환경 자동 생성 및 Python 패키지 설치가 진행됩니다.
3. `tubesync-plex-metadata.py` 스크립트가 실행되어 Plex 메타데이터를 동기화합니다.

> **참고:** `tubesync-plex.sh` 파일에 실행 권한이 필요합니다.

```bash
chmod +x tubesync-plex.sh
```

---

## 설정 파일 (config.json)

스크립트 실행 시 `config.json`이 없으면 자동 생성됩니다. 생성된 파일을 열어 Plex 설정을 입력하고 다시 실행하세요.

```json
{
    "_comment": {
        "plex_base_url": "Your Plex server base URL, e.g., http://localhost:32400",
        "plex_token": "Your Plex server token",
        "plex_library_names": ["Library1", "Library2"],
        "silent": "true or false, whether to suppress logs",
        "detail": "true or false, whether to show detailed update logs",
        "subtitles": "true or false, whether to upload subtitles if available"
    },
    "plex_base_url": "",
    "plex_token": "",
    "plex_library_names": [""],
    "silent": false,
    "detail": false,
    "subtitles": false
}
```

* `plex_library_names`: 배열 형태로 여러 라이브러리 지정 가능
* `silent`: true로 설정 시 로그 출력 최소화
* `detail`: true로 설정 시 세부 업데이트 로그 출력
* `subtitles`: true로 설정 시 VTT 자막 파일이 있는 경우 업로드

---

## 사용법

```bash
./tubesync-plex.sh
```

* 기본적으로 `config.json`을 읽어서 설정 적용
* 환경변수로 다른 설정 파일 사용 가능:

```bash
CONFIG_FILE="/path/to/config.json" ./tubesync-plex.sh
```

---

## 권한

* 스크립트 실행 권한 필요
* Plex 서버 접근 권한 필요 (API 토큰)

---

## 주기적 실행 (Cron)

예시: 매일 오전 3시에 실행

```cron
0 3 * * * /path/to/tubesync-plex.sh
```

---

## 참고

* 스크립트는 Plex 라이브러리에서만 메타데이터를 업데이트하며, 로컬 NFO 파일은 적용 후 삭제됩니다.
* 업데이트 없는 항목은 로그에 기본적으로 표시되지 않으며, `--detail` 옵션에서 확인 가능합니다.
