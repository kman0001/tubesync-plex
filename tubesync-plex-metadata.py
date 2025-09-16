import os
import json
import time
import threading
from pathlib import Path
from plexapi.server import PlexServer
import lxml.etree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import argparse

# -----------------------------
# Command-line argument parsing
# -----------------------------
parser = argparse.ArgumentParser(description="TubeSync Plex Metadata Sync")
parser.add_argument("--disable-watchdog", action="store_true", help="Disable folder watching")
parser.add_argument("--config", type=str, default=None, help="Path to config.json")
args = parser.parse_args()

DISABLE_WATCHDOG = args.disable_watchdog

# -----------------------------
# Config file
# -----------------------------
CONFIG_FILE = args.config or os.environ.get("CONFIG_FILE", "config.json")
CONFIG_FILE = os.path.abspath(CONFIG_FILE)

# Default config template
default_config = {
    "_comment": {
        "plex_base_url": "Plex server URL, e.g., http://localhost:32400",
        "plex_token": "Plex server token",
        "plex_library_names": ["TV Shows","Movies"],
        "silent": "true/false",
        "detail": "true/false",
        "subtitles": "true/false",
        "threads": "number of threads, e.g., 8",
        "max_concurrent_requests": "concurrent Plex API requests, e.g., 4",
        "request_delay": "delay between API requests (seconds), e.g., 0.1",
        "watch_folders": "enable folder watching, true/false",
        "watch_debounce_delay": "debounce time for folder watching (seconds), e.g., 2"
    },
    "plex_base_url": "",
    "plex_token": "",
    "plex_library_names": ["TV Shows","Movies"],
    "silent": False,
    "detail": False,
    "subtitles": False,
    "threads": 8,
    "max_concurrent_requests": 4,
    "request_delay": 0.1,
    "watch_folders": False,
    "watch_debounce_delay": 2
}

# If config.json does not exist, create it and exit
if not os.path.exists(CONFIG_FILE):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    exit(0)

# Load config
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# Disable watchdog if command-line option is set
if DISABLE_WATCHDOG:
    config["watch_folders"] = False

# -----------------------------
# Connect to Plex server
# -----------------------------
try:
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
except Exception as e:
    print(f"[ERROR] Failed to connect to Plex: {e}")
    exit(1)

# -----------------------------
# Global variables
# -----------------------------
VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
api_semaphore = threading.Semaphore(config.get("max_concurrent_requests", 2))
request_delay = config.get("request_delay", 0.1)
threads = config.get("threads", 4)
detail = config.get("detail", False)
subtitles_enabled = config.get("subtitles", False)
watch_folders_enabled = config.get("watch_folders", False)
watch_debounce_delay = config.get("watch_debounce_delay", 2)

LANG_MAP = {
    "eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr",
    "spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"
}
def map_lang(code): return LANG_MAP.get(code.lower(),"und")

# -----------------------------
# Subtitle extraction and upload
# -----------------------------
def extract_subtitles(video_path):
    base,_ = os.path.splitext(video_path)
    srt_files=[]
    ffprobe_cmd = ["ffprobe","-v","error","-select_streams","s",
                   "-show_entries","stream=index:stream_tags=language,codec_name",
                   "-of","json",video_path]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags", {}).get("language", "und"))
            srt = f"{base}.{lang}.srt"
            if os.path.exists(srt): continue
            subprocess.run(["ffmpeg","-y","-i",video_path,f"-map","0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(srt): srt_files.append((srt, lang))
    except Exception as e:
        print(f"[ERROR] ffprobe/ffmpeg failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep, srt_files):
    for srt, lang in srt_files:
        try:
            with api_semaphore:
                ep.uploadSubtitles(srt, language=lang)
                time.sleep(request_delay)
            if detail: print(f"[SUBTITLE] Uploaded: {srt}")
        except Exception as e:
            print(f"[ERROR] Subtitle upload failed: {srt} - {e}")

# -----------------------------
# Apply NFO metadata
# -----------------------------
def apply_nfo(ep, file_path):
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0: 
        return False
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title", "")
        plot = root.findtext("plot", "")
        aired = root.findtext("aired", "")
        if detail: print(f"[-] Applying NFO: {file_path} -> {title}")
        ep.editTitle(title, locked=True)
        ep.editSortTitle(aired, locked=True)
        ep.editSummary(plot, locked=True)
        if subtitles_enabled:
            srt_files = extract_subtitles(file_path)
            if srt_files: upload_subtitles(ep, srt_files)
        os.remove(nfo_path)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to apply NFO: {nfo_path} - {e}")
        return False

# -----------------------------
# Process single file
# -----------------------------
def process_file(file_path):
    if not file_path.lower().endswith(VIDEO_EXTS): return False
    abs_path = os.path.abspath(file_path)
    found = None

    for lib in config["plex_library_names"]:
        try:
            section = plex.library.section(lib)
        except: continue

        if getattr(section, "TYPE", "").lower() == "show":
            for show in section.all():
                for season in getattr(show, "seasons", lambda: [])():
                    for ep in getattr(season, "episodes", lambda: [])():
                        for part in getattr(ep, "iterParts", lambda: [])():
                            if os.path.abspath(part.file) == abs_path:
                                found = ep
                                break
                        if found: break
                    if found: break
                if found: break
        else:
            for ep in section.all():
                for part in getattr(ep, "iterParts", lambda: [])():
                    if os.path.abspath(part.file) == abs_path:
                        found = ep
                        break
                if found: break

        if found: break

    if not found:
        if detail: print(f"[WARN] Episode not found for: {file_path}")
        return False
    return apply_nfo(found, abs_path)

# -----------------------------
# Main processing
# -----------------------------
def main():
    total = 0
    all_files = []
    for lib in config["plex_library_names"]:
        try:
            section = plex.library.section(lib)
        except: continue
        paths = getattr(section, "locations", [])
        for p in paths:
            for root, dirs, files in os.walk(p):
                for f in files:
                    all_files.append(os.path.join(root, f))
    if detail: print(f"[INFO] Total files to process: {len(all_files)}")

    with ThreadPoolExecutor(max_workers=threads) as ex:
        futures = [ex.submit(process_file, f) for f in all_files]
        for fut in as_completed(futures):
            if fut.result(): total += 1

    if not config.get("silent", False):
        print(f"[INFO] Total items updated: {total}")

# -----------------------------
# Watchdog for NFO files
# -----------------------------
class NFOHandler(FileSystemEventHandler):
    def __init__(self, debounce=2):
        self.debounce = debounce
        self.timer = None

    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith(".nfo"): return
        if self.timer and self.timer.is_alive():
            self.timer.cancel()
        self.timer = threading.Timer(self.debounce, main)
        self.timer.start()

    def on_modified(self, event):
        self.on_created(event)

# -----------------------------
# Execute
# -----------------------------
if __name__ == "__main__":
    main()

    if watch_folders_enabled:
        observer = Observer()
        for lib in config["plex_library_names"]:
            try:
                section = plex.library.section(lib)
            except: continue
            paths = getattr(section, "locations", [])
            for path in paths:
                observer.schedule(NFOHandler(debounce=watch_debounce_delay), path, recursive=True)
        print(f"[INFO] Started watching NFO files in: {config['plex_library_names']}")
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
