# Batch JSON to NFO Converter (UTF-8 지원)

이 스크립트는 `yt-dlp`로 다운로드한 `info.json` 파일을 기반으로 **Plex/Kodi 호환 NFO 파일**을 자동으로 생성합니다.
UTF-8 인코딩을 포함하여 일본어, 한글, 특수문자가 깨지지 않도록 처리합니다.
같은 이름의 이미지 파일(`.jpg`, `.png`, `.jpeg`, `.webp`)이 존재하면 NFO의 섬네일로 자동 적용됩니다.
YAML 템플릿과 JSON 폴더를 **커맨드라인 옵션**으로 지정할 수 있습니다.

---

## 폴더 구조 예시

```
/project
  ├─ videos/                     # info.json 파일과 이미지 파일 저장
  │    ├─ video1.info.json
  │    ├─ video1.jpg
  │    ├─ video2.info.json
  │    └─ video2.webp
  ├─ tubesync.yaml               # YAML 템플릿
  └─ json_to_nfo.py              # 변환 스크립트 (UTF-8 포함)
```

---

## 요구 사항

* Python 3.7 이상
* PyYAML 설치

```bash
pip install pyyaml
```

---

## 사용 방법

1. `videos` 폴더에 `yt-dlp`로 생성된 `.info.json` 파일과 이미지 파일을 준비합니다.

2. YAML 템플릿 파일을 작성합니다.
   기본 구조 예시는 다음과 같습니다:

```yaml
title: "{title}"
showtitle: "{showtitle}"
season: "{season}"
episode: "{episode}"
ratings:
  - name: "youtube"
    max: 5
    default: true
    value: "{rating_value|default:0}"
    votes: "{rating_votes|default:0}"
plot: "{description}"
thumb: "{thumbnail}"
runtime: "{duration}"
id: "{id}"
uniqueid:
  type: "youtube"
  default: true
  value: "{id}"
studio: "{uploader}"
aired: "{upload_date|date:%Y-%m-%d}"
dateadded: "{dateadded|default:now:%Y-%m-%d %H:%M:%S}"
genre: "{genre}"
```

3. 스크립트 실행:

```bash
# 기본 옵션
python json_to_nfo.py

# YAML 템플릿 지정
python json_to_nfo.py --yaml /volume1/docker/tubesync/nfo/tubesync.yaml

# JSON 폴더와 YAML 모두 지정
python json_to_nfo.py --json-folder /volume1/docker/tubesync/nfo/videos --yaml /volume1/docker/tubesync/nfo/tubesync.yaml
```

* `videos` 폴더 내 모든 `.json` 파일에 대해 NFO 파일이 생성됩니다.
* `.info.json`에서 `.info`는 제거되고 `.nfo`로 저장됩니다.
* 같은 이름의 이미지 파일이 있으면 `<thumb>`에 적용됩니다.
* 이미지가 없으면 info.json 내부 `thumbnail` URL이 사용됩니다.

---

## Plex/Kodi 호환

* 생성된 NFO 파일은 Plex와 Kodi에서 TV 시리즈 및 영화 메타데이터로 바로 사용 가능합니다.
* UTF-8 인코딩 포함으로 일본어, 한글, 특수문자도 깨지지 않고 표시됩니다.
* 섬네일, 제목, 시즌/에피소드, 줄거리, 스튜디오, 장르, 평가 정보가 포함됩니다.

---

## 주의 사항

* JSON 파일과 이미지 파일 이름이 정확히 일치해야 섬네일이 적용됩니다.
* `.info.json` 파일명에서 `.info`는 자동으로 제거됩니다.
* 폴더 전체를 처리하므로, 불필요한 JSON 파일은 제거 후 실행하세요.

---

## 추가 기능

* YAML 템플릿과 JSON 폴더를 옵션으로 지정 가능
* `yt-dlp` 다운로드 후 **자동 NFO 생성(Post-hook)** 으로 연동 가능
* UTF-8 인코딩 포함으로 멀티바이트 문자 안전
