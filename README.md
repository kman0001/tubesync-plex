# TubeSync Plex Metadata Sync (Personal Update)

This repository is a **personal fork** of [tgouverneur/tubesync-plex](https://github.com/tgouverneur/tubesync-plex) and has been updated for **personal use**.

## Key Changes in this Fork
- Simplified default log output
- Added `-d / --detail` option for detailed metadata updates
- Disallow simultaneous use of `-s / --silent` and `-d / --detail` options

> ⚠️ **Note:** This fork is maintained for personal purposes and may differ from the original repository.

====

# TubeSync Plex Metadata Tool

TubeSync Plex Metadata Tool은 Plex 라이브러리의 에피소드 메타데이터를 NFO 파일 기반으로 업데이트하는 Python 도구입니다.

---

## 요구 사항

* Python 3.8 이상
* pip
* plexapi
* lxml

---

## 설치 방법

1. GitHub 저장소를 클론합니다.

```bash
git clone https://github.com/kman0001/tubesync-plex.git
cd tubesync-plex
```

2. 가상 환경 생성 및 활성화 (선택 사항)

```bash
python3 -m venv venv
source venv/bin/activate
```

3. 의존성 설치

```bash
pip install -r requirements.txt
```

---

## 사용법 (Python 스크립트)

```bash
python tubesync-plex-metadata.py [-c CONFIG] [-s] [-d] [--all] [--subtitles]
```

옵션:

* `-c`, `--config`: 설정 파일 경로 (기본: `./config.ini`)
* `-s`, `--silent`: 로그 출력 최소화
* `-d`, `--detail`: 상세 로그 출력
* `--all`: 라이브러리 전체 업데이트
* `--subtitles`: 동영상에 대응하는 자막 자동 업로드

> `-s`와 `-d`는 동시에 사용할 수 없습니다.

---

## 사용법 (쉘 스크립트)

저장소에 포함된 `tubesync-plex.sh`를 사용하면, 다음을 자동으로 처리합니다:

1. GitHub 저장소 업데이트 (`git pull`)
2. Python 가상 환경 확인 및 생성
3. Python 의존성 설치/업데이트
4. TubeSync Plex 스크립트 실행

```bash
bash tubesync-plex.sh
```

> 쉘 스크립트에서 옵션을 전달하려면:
>
> * BASE_DIR="/your/dir/to/tubesync-plex"
>   작업 디렉토리를 본인의 환경에 맞게 변경합니다.
> * 스크립트 내부의 Python 실행 부분을 수정하여 인자를 추가할 수 있습니다.
>   예: `"$BASE_DIR/venv/bin/python" "$BASE_DIR/tubesync-plex-metadata.py" --all --subtitles`
> * 필요에 따라 `--silent` 또는 `--detail` 옵션도 추가 가능합니다.
> * 쉘 스크립트 파일을 텍스트 편집기에서 열어 원하는 옵션을 직접 수정하면 됩니다.

---

## 로그

* NFO가 성공적으로 적용되면 업데이트된 메타데이터 수가 출력됩니다.
* NFO가 손상되거나 읽을 수 없는 경우, 오류 로그가 출력되고 NFO는 삭제되지 않습니다.
* 업데이트가 정상적으로 완료되면, 관련 NFO 파일은 삭제됩니다.

---

## 지원하는 비디오 파일 확장자

`.mkv`, `.mp4`, `.avi`, `.mov`, `.wmv`, `.flv`, `.m4v`

