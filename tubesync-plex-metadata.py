import os
import sys
import json
from plexapi.server import PlexServer
import lxml.etree as ET

# -----------------------------
# CONFIG_FILE 설정
# -----------------------------
CONFIG_FILE = os.environ.get("CONFIG_FILE", "config.json")
CONFIG_FILE = os.path.abspath(CONFIG_FILE)

# -----------------------------
# 기본 config
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

# -----------------------------
# config.json 생성
# -----------------------------
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

# -----------------------------
# config 로드
# -----------------------------
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# -----------------------------
# Plex 연결
# -----------------------------
try:
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
except Exception as e:
    print(f"[ERROR] Plex 연결 실패: {e}")
    sys.exit(1)

# -----------------------------
# NFO 업데이트
# -----------------------------
video_extensions = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

def main():
    updated_count = 0

    for library_name in config["plex_library_names"]:
        try:
            section = plex.library.section(library_name)
        except Exception as e:
            print(f"[ERROR] 라이브러리 '{library_name}' 접근 실패: {e}")
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
                            lockedFields=["title", "originallyAvailableAt", "summary"]
                        )

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
