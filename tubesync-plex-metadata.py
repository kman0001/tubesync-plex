import os
import sys
import json
import subprocess
from plexapi.server import PlexServer
import lxml.etree as ET
import platform

# -----------------------------
# CONFIG_FILE setting
# -----------------------------
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

# -----------------------------
# Create config.json if missing
# -----------------------------
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

# -----------------------------
# Load config
# -----------------------------
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# -----------------------------
# Connect to Plex
# -----------------------------
try:
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
except Exception as e:
    print(f"[ERROR] Failed to connect to Plex: {e}")
    sys.exit(1)

# -----------------------------
# Set ffmpeg/ffprobe paths depending on OS
# -----------------------------
FFMPEG_CMD = "ffmpeg"
FFPROBE_CMD = "ffprobe"

if platform.system() == "Windows":
    # On Windows, use absolute path if needed
    FFMPEG_CMD = os.environ.get("FFMPEG_PATH", "ffmpeg.exe")
    FFPROBE_CMD = os.environ.get("FFPROBE_PATH", "ffprobe.exe")

# -----------------------------
# Map language codes (ffmpeg → Plex ISO 639-1)
# -----------------------------
LANG_MAP = {
    "eng": "en",
    "jpn": "ja",
    "kor": "ko",
    "fre": "fr",
    "fra": "fr",
    "spa": "es",
    "ger": "de",
    "deu": "de",
    "ita": "it",
    "chi": "zh",
    "und": "und"
}

def map_language_code(code):
    return LANG_MAP.get(code.lower(), "und")

# -----------------------------
# Extract embedded MKV subtitles (multiple tracks)
# -----------------------------
def extract_subtitles_multi(video_path):
    base, ext = os.path.splitext(video_path)
    extracted_files = []

    try:
        probe_cmd = [
            FFPROBE_CMD,
            "-v", "error",
            "-select_streams", "s",
            "-show_entries", "stream=index:stream_tags=language",
            "-of", "json",
            video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        import json as js
        streams = js.loads(result.stdout).get("streams", [])
    except Exception as e:
        print(f"[ERROR] ffprobe failed: {video_path} - {e}")
        return extracted_files

    for stream in streams:
        idx = stream.get("index")
        lang_code = map_language_code(stream.get("tags", {}).get("language", "und"))
        srt_file = f"{base}.{lang_code}.srt"
        if os.path.exists(srt_file):
            continue  # Skip if already exists
        try:
            cmd = [
                FFMPEG_CMD,
                "-y",
                "-i", video_path,
                "-map", f"0:s:{idx}",
                srt_file
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(srt_file):
                extracted_files.append((srt_file, lang_code))
        except Exception as e:
            print(f"[ERROR] Subtitle extraction failed: {video_path} track {idx} - {e}")

    return extracted_files

# -----------------------------
# Upload subtitles to Plex
# -----------------------------
def add_subtitles_to_plex(part, srt_files):
    for srt_file, lang in srt_files:
        try:
            part.uploadSubtitles(srt_file, language=lang)
        except Exception as e:
            print(f"[ERROR] Failed to upload subtitles to Plex {srt_file}: {e}")

# -----------------------------
# Update NFO metadata and handle subtitles
# -----------------------------
video_extensions = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

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

                        # Update Plex metadata
                        ep.edit(
                            title=title if title else None,
                            originallyAvailableAt=aired if aired else None,
                            summary=plot if plot else None,
                            lockedFields=["title", "originallyAvailableAt", "summary"]
                        )

                        # Handle subtitles
                        if config.get("subtitles", False) and part.file.lower().endswith(".mkv"):
                            extracted = extract_subtitles_multi(part.file)
                            if extracted:
                                add_subtitles_to_plex(part, extracted)
                                if config.get("detail", False):
                                    for srt_file, _ in extracted:
                                        print(f"[SUBTITLE] Registered {srt_file} to Plex")

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
