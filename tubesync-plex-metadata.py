import os
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
    exit(0)

# -----------------------------
# config 로드
# -----------------------------
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# -----------------------------
# Plex 연결 및 NFO 업데이트
# -----------------------------
video_extensions = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

def main():
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
    updated_count = 0

    for library_name in config["plex_library_names"]:
        section = plex.library.section(library_name)
        for ep in section.search(libtype="episode"):
            for part in ep.iterParts():
                nfo_path = os.path.splitext(part.file)[0] + ".nfo"
                if os.path.exists(nfo_path):
                    try:
                        tree = ET.parse(nfo_path, parser=ET.XMLParser(recover=True))
                        root = tree.getroot()
                        title = root.findtext("title", default="")
                        aired = root.findtext("aired", default="")
                        plot = root.findtext("plot", default="")
                        ep.editTitle(title, locked=True)
                        ep.editSortTitle(aired, locked=True)
                        ep.editSummary(plot, locked=True)
                        updated_count += 1
                        os.remove(nfo_path)
                    except Exception as e:
                        print(f"[ERROR] {nfo_path}: {e}")

    if not config.get("silent", False):
        print(f"[INFO] Total episodes updated: {updated_count}")

if __name__ == "__main__":
    main()
