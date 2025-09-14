import os
import sys
import json
import subprocess
from plexapi.server import PlexServer
import lxml.etree as ET
import platform
import shutil

CONFIG_FILE = os.environ.get("CONFIG_FILE", "config.json")
CONFIG_FILE = os.path.abspath(CONFIG_FILE)

# -----------------------------
# Default config
# -----------------------------
default_config = {
    "_comment": {
        "plex_base_url": "Your Plex server base URL, e.g., http://localhost:32400",
        "plex_token": "Your Plex server token",
        "plex_library_names": '["TV Shows", "Anime"]',
        "silent": "true or false",
        "detail": "true or false",
        "subtitles": "true or false"
    },
    "plex_base_url": "",
    "plex_token": "",
    "plex_library_names": [""],
    "silent": False,
    "detail": False,
    "subtitles": False
}

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

try:
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
except Exception as e:
    print(f"[ERROR] Failed to connect to Plex: {e}")
    sys.exit(1)

video_extensions = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
FFMPEG_CMD = "ffmpeg"
FFPROBE_CMD = "ffprobe"
system_platform = platform.system()

# -----------------------------
# ffmpeg/ffprobe check (subtitles=True)
# -----------------------------
def check_ffmpeg_tools():
    if not config.get("subtitles", False):
        return

    global FFMPEG_CMD, FFPROBE_CMD

    if system_platform == "Windows":
        ffmpeg_env = os.environ.get("FFMPEG_PATH")
        ffprobe_env = os.environ.get("FFPROBE_PATH")
        if ffmpeg_env and not os.path.isfile(ffmpeg_env):
            print(f"[ERROR] FFMPEG_PATH 환경 변수 경로가 존재하지 않음: {ffmpeg_env}")
            sys.exit(1)
        if ffprobe_env and not os.path.isfile(ffprobe_env):
            print(f"[ERROR] FFPROBE_PATH 환경 변수 경로가 존재하지 않음: {ffprobe_env}")
            sys.exit(1)
        if ffmpeg_env: FFMPEG_CMD = ffmpeg_env
        if ffprobe_env: FFPROBE_CMD = ffprobe_env

    for cmd in [FFMPEG_CMD, FFPROBE_CMD]:
        path = shutil.which(cmd)
        if path is None:
            print(f"[ERROR] '{cmd}' 실행 파일을 찾을 수 없습니다.")
            sys.exit(1)
        elif config.get("detail", False):
            try:
                version = subprocess.run([cmd, "-version"], capture_output=True, text=True)
                print(f"[INFO] {cmd} found: {version.stdout.splitlines()[0]} (path: {path})")
            except:
                print(f"[INFO] {cmd} found at {path}, 버전 정보 확인 불가")

check_ffmpeg_tools()

# -----------------------------
# Language mapping
# -----------------------------
LANG_MAP = {
    "eng": "en", "jpn": "ja", "kor": "ko", "fre": "fr", "fra": "fr",
    "spa": "es", "ger": "de", "deu": "de", "ita": "it", "chi": "zh", "und": "und"
}
def map_language_code(code):
    return LANG_MAP.get(code.lower(), "und")

# -----------------------------
# Extract subtitles (only extractable tracks)
# -----------------------------
def extract_subtitles_multi(video_path):
    base, _ = os.path.splitext(video_path)
    extracted_files = []

    try:
        probe_cmd = [
            FFPROBE_CMD, "-v", "error", "-select_streams", "s",
            "-show_entries", "stream=index:stream_tags=language,codec_name",
            "-of", "json", video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        streams = json.loads(result.stdout).get("streams", [])
    except Exception as e:
        print(f"[ERROR] ffprobe failed: {video_path} - {e}")
        return extracted_files

    for stream in streams:
        idx = stream.get("index")
        codec = stream.get("codec_name", "")
        lang_code = map_language_code(stream.get("tags", {}).get("language", "und"))
        srt_file = f"{base}.{lang_code}.srt"
        if os.path.exists(srt_file):
            continue

        try:
            # FFmpeg가 SRT로 변환 가능한 경우만 추출
            cmd = [FFMPEG_CMD, "-y", "-i", video_path, "-map", f"0:s:{idx}", srt_file]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if os.path.exists(srt_file):
                extracted_files.append((srt_file, lang_code))
                if config.get("detail", False):
                    print(f"[SUBTITLE] Extracted {srt_file}")
            else:
                print(f"[WARN] 자막 트랙({codec}) 추출 불가: {video_path}")

        except Exception as e:
            print(f"[ERROR] Subtitle extraction failed: {video_path} track {idx} - {e}")

    return extracted_files

def add_subtitles_to_plex(part, srt_files):
    for srt_file, lang in srt_files:
        try:
            part.uploadSubtitles(srt_file, language=lang)
            if config.get("detail", False):
                print(f"[SUBTITLE] Uploaded {srt_file} to Plex")
        except Exception as e:
            print(f"[ERROR] Failed to upload subtitles {srt_file}: {e}")

# -----------------------------
# Main loop
# -----------------------------
def main():
    updated_count = 0
    for library_name in config["plex_library_names"]:
        try:
            section = plex.library.section(library_name)
        except Exception as e:
            print(f"[ERROR] Failed to access library '{library_name}': {e}")
            continue

        for ep in section.search(libtype="episode"):
            for part in ep.iterParts():
                if not part.file.lower().endswith(video_extensions):
                    continue

                nfo_path = os.path.splitext(part.file)[0] + ".nfo"
                if os.path.exists(nfo_path):
                    try:
                        tree = ET.parse(nfo_path, parser=ET.XMLParser(recover=True))
                        root = tree.getroot()
                        title = root.findtext("title", default="")
                        aired = root.findtext("aired", default="")
                        plot = root.findtext("plot", default="")

                        ep.edit(
                            title=title if title else None,
                            originallyAvailableAt=aired if aired else None,
                            summary=plot if plot else None,
                            lockedFields=["title","originallyAvailableAt","summary"]
                        )

                        if config.get("subtitles", False):
                            extracted = extract_subtitles_multi(part.file)
                            if extracted:
                                add_subtitles_to_plex(part, extracted)

                        updated_count += 1
                        if config.get("detail", False):
                            print(f"[UPDATED] {part.file} → {title}")

                        os.remove(nfo_path)
                    except Exception as e:
                        print(f"[ERROR] {nfo_path}: {e}")

    if not config.get("silent", False):
        print(f"[INFO] Total episodes updated: {updated_count}")

if __name__ == "__main__":
    main()
