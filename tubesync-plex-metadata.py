import os
import json
from plexapi.server import PlexServer
import lxml.etree as ET

video_extensions = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
CONFIG_FILE = "config.json"

# Default config structure with comments
default_config = {
    "_comment": {
        "plex_base_url": "Your Plex server base URL, e.g., http://localhost:32400",
        "plex_token": "Your Plex server token",
        "plex_library_name": "Name of the library to sync metadata",
        "silent": "true or false, whether to suppress logs",
        "detail": "true or false, whether to show detailed update logs",
        "syncAll": "true or false, whether to update all items",
        "subtitles": "true or false, whether to upload subtitles if available (not implemented yet)"
    },
    "plex_base_url": "",
    "plex_token": "",
    "plex_library_name": "",
    "silent": False,
    "detail": False,
    "syncAll": False,
    "subtitles": False
}

# Create config.json if missing
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it with your Plex settings and rerun the script.")
    exit(0)

# Load config
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

def main():
    plex_base_url = config["plex_base_url"]
    plex_token = config["plex_token"]
    plex_library_name = config["plex_library_name"]

    # Plex connection with error handling
    try:
        plex = PlexServer(plex_base_url, plex_token)
    except Exception as e:
        print(f"[ERROR] Failed to connect to Plex server: {e}")
        exit(1)

    try:
        section = plex.library.section(plex_library_name)
    except Exception as e:
        print(f"[ERROR] Failed to access library '{plex_library_name}': {e}")
        exit(1)

    title_filter = '' if config.get("syncAll", False) else 'Episode '
    updated_count = 0

    for ep in section.search(title=title_filter, libtype='episode'):
        for part in ep.iterParts():
            if not part.file.lower().endswith(video_extensions):
                continue

            nfo_path = os.path.splitext(part.file)[0] + ".nfo"
            if os.path.exists(nfo_path):
                if config.get("detail", False):
                    print(f"[-] Parsing NFO: {nfo_path}")
                try:
                    parser = ET.XMLParser(recover=True)
                    tree = ET.parse(nfo_path, parser=parser)
                    root = tree.getroot()
                except ET.XMLSyntaxError as e:
                    print(f"[ERROR] Malformed NFO: {nfo_path}. Details: {e}")
                    continue
                except Exception as e:
                    print(f"[ERROR] Failed to read NFO: {nfo_path}. Details: {e}")
                    continue

                if root is None:
                    continue

                title = root.findtext('title', default='')
                aired = root.findtext('aired', default='')
                plot = root.findtext('plot', default='')

                if config.get("detail", False):
                    print(f"[-] Updating: {title} - Aired: {aired}")

                try:
                    ep.editTitle(title, locked=True)
                    ep.editSortTitle(aired, locked=True)
                    ep.editSummary(plot, locked=True)
                    updated_count += 1
                    # Delete NFO only after successful update
                    try:
                        os.remove(nfo_path)
                        if not config.get("silent", False):
                            print(f"[-] Deleted NFO: {nfo_path}")
                    except Exception as e:
                        print(f"[ERROR] Failed to delete NFO: {nfo_path}. Details: {e}")
                except Exception as e:
                    print(f"[ERROR] Failed to update Plex metadata for {ep.title}: {e}")

    if not config.get("silent", False):
        print(f"[INFO] {updated_count} metadata items updated.")

if __name__ == "__main__":
    main()
