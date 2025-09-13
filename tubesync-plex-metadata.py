import os
import argparse
import json
from plexapi.server import PlexServer
import lxml.etree as ET

video_extensions_default = [".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v"]

# 환경변수 CONFIG_FILE 우선, 없으면 ./config.json
CONFIG_FILE = os.environ.get("CONFIG_FILE", "./config.json")

# config.json이 없으면 생성 후 안내
if not os.path.exists(CONFIG_FILE):
    default_config = {
        "base_dir": ".",
        "plex_base_url": "",
        "plex_token": "",
        "plex_library_name": "",
        "video_extensions": video_extensions_default
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(default_config, f, indent=4)
    print(f"[INFO] Config file created at {CONFIG_FILE}. Please fill in the required fields and rerun.")
    exit(1)

# config.json 로드
with open(CONFIG_FILE) as f:
    config = json.load(f)

video_extensions = tuple(config.get("video_extensions", video_extensions_default))
base_dir = config.get("base_dir", ".")

def main(silent, detail, syncAll, subtitles):
    plex_base_url = config["plex_base_url"]
    plex_token = config["plex_token"]
    plex_library_name = config["plex_library_name"]

    plex = PlexServer(plex_base_url, plex_token)
    section = plex.library.section(plex_library_name)

    title_filter = 'Episode ' if not syncAll else ''

    updated_count = 0

    for ep in section.search(title=title_filter, libtype='episode'):
        for part in ep.iterParts():
            if not part.file.lower().endswith(video_extensions):
                continue

            nfo_file = os.path.splitext(part.file)[0] + ".nfo"
            if os.path.exists(nfo_file):
                if detail:
                    print(f"[-] Parsing NFO: {nfo_file}")
                try:
                    parser = ET.XMLParser(recover=True)
                    tree = ET.parse(nfo_file, parser=parser)
                except ET.XMLSyntaxError as e:
                    print(f"[ERROR] Malformed NFO: {nfo_file}, {e}")
                    continue
                except Exception as e:
                    print(f"[ERROR] Failed to read NFO {nfo_file}: {e}")
                    continue

                root = tree.getroot()
                if root is None:
                    continue

                title = root.findtext("title", default="")
                aired = root.findtext("aired", default="")
                plot = root.findtext("plot", default="")

                if detail:
                    print(f"[-] Updating: {title} - {aired}")

                ep.editTitle(title, locked=True)
                ep.editSortTitle(aired, locked=True)
                ep.editSummary(plot, locked=True)
                updated_count += 1

                # NFO 삭제
                try:
                    os.remove(nfo_file)
                    if not silent:
                        print(f"[-] Deleted NFO: {nfo_file}")
                except Exception as e:
                    print(f"[ERROR] Failed to delete NFO '{nfo_file}': {e}")

    if not silent:
        print(f"[INFO] {updated_count} metadata items updated.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TubeSync Plex Media Metadata sync tool")
    parser.add_argument("-s", "--silent", action="store_true", help="Silent mode")
    parser.add_argument("-d", "--detail", action="store_true", help="Show detailed logs")
    parser.add_argument("--all", action="store_true", help="Update all items")
    parser.add_argument("--subtitles", action="store_true", help="Upload subtitles if found")
    args = parser.parse_args()

    if args.silent and args.detail:
        print("Error: --silent and --detail cannot be used together.")
        exit(1)

    main(args.silent, args.detail, args.all, args.subtitles)
