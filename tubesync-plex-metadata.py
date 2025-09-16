#!/usr/bin/env python3
import os
import sys
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
# Base directories
# -----------------------------
BASE_DIR = os.environ.get("BASE_DIR", "/app")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = args.config or os.path.join(CONFIG_DIR, "config.json")

# config.json이 있는 디렉토리를 기준으로 캐시 생성
CACHE_FILE = os.path.join(os.path.dirname(CONFIG_FILE), "tubesync_cache.json")

# -----------------------------
# Default config
# -----------------------------
default_config = {
    "_comment": {
        "plex_base_url": "Plex server URL, e.g., http://localhost:32400",
        "plex_token": "Plex server token",
        "plex_library_ids": "List of Plex library IDs to sync, e.g., [10,21,35]",
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
    "plex_library_ids": [],
    "silent": False,
    "detail": False,
    "subtitles": False,
    "threads": 8,
    "max_concurrent_requests": 4,
    "request_delay": 0.1,
    "watch_folders": False,
    "watch_debounce_delay": 2
}

# Create config.json if missing
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

# Load config
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

if DISABLE_WATCHDOG:
    config["watch_folders"] = False

# -----------------------------
# Plex connection
# -----------------------------
try:
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
except Exception as e:
    print(f"[ERROR] Failed to connect to Plex: {e}")
    sys.exit(1)

# -----------------------------
# Globals
# -----------------------------
VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
api_semaphore = threading.Semaphore(config.get("max_concurrent_requests", 2))
request_delay = config.get("request_delay", 0.1)
threads = config.get("threads", 4)
detail = config.get("detail", False)
subtitles_enabled = config.get("subtitles", False)
watch_folders_enabled = config.get("watch_folders", False)
watch_debounce_delay = config.get("watch_debounce_delay", 2)
processed_files = set()

# -----------------------------
# Cache handling
# -----------------------------
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}
    # 최초 생성 시 저장
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        if detail:
            print(f"[CACHE] Created empty cache at {CACHE_FILE}")
    except Exception as e:
        print(f"[ERROR] Failed to create cache: {e}")

def save_cache(cache_dict):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_dict, f, indent=2, ensure_ascii=False)
        if detail:
            print(f"[CACHE] Saved cache to {CACHE_FILE}, total items: {len(cache_dict)}")
    except Exception as e:
        print(f"[ERROR] Failed to save cache: {e}")

def update_cache(file_path, plex_item):
    if plex_item is None: return
    cache[file_path] = plex_item.key
    save_cache(cache)

# -----------------------------
# Subtitles
# -----------------------------
LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr","spa":"es",
            "ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}
def map_lang(code): return LANG_MAP.get(code.lower(),"und")

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
def apply_nfo(ep, file_path, subtitles_enabled=False, detail=False, cache=None):
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title", "")
        plot = root.findtext("plot", "")
        aired = root.findtext("aired", "")

        if detail:
            print(f"[-] Applying NFO: {file_path} -> {title}")

        ep.editTitle(title, locked=True)
        ep.editSortTitle(aired, locked=True)
        ep.editSummary(plot, locked=True)

        if subtitles_enabled:
            srt_files = extract_subtitles(file_path)
            if srt_files:
                upload_subtitles(ep, srt_files)

        if cache is not None:
            cache[str(file_path)] = ep.key

        try:
            nfo_path.unlink()
            if detail:
                print(f"[-] Deleted NFO: {nfo_path}")
        except Exception as e:
            print(f"[WARN] Failed to delete NFO file: {nfo_path} - {e}")

        return True

    except ET.XMLSyntaxError as e:
        print(f"[!] XMLSyntaxError: Malformed XML in {nfo_path}, skipping. Details: {e}")
        return False
    except Exception as e:
        print(f"[!] Unexpected error processing {nfo_path}, skipping. Details: {e}")
        return False

# -----------------------------
# Process single file
# -----------------------------
def process_file(file_path):
    abs_path = os.path.abspath(file_path)
    if abs_path in processed_files: 
        return False
    if not file_path.lower().endswith(VIDEO_EXTS): 
        return False

    plex_item = None
    key = cache.get(abs_path)
    if key:
        try:
            plex_item = plex.fetchItem(key)
        except:
            plex_item = None

    if not plex_item:
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except:
                continue
            section_type = getattr(section, "TYPE", "").lower()
            if section_type == "show":
                results = section.search(libtype="episode")
            elif section_type in ("movie","video"):
                results = section.search(libtype="movie")
            else:
                continue
            for item in results:
                for part in item.iterParts():
                    if os.path.abspath(part.file) == abs_path:
                        plex_item = item
                        break
                if plex_item: break
            if plex_item: break

    if not plex_item:
        if detail: 
            print(f"[WARN] Item not found for: {file_path}")
        return False

    success = apply_nfo(
        plex_item,
        abs_path,
        subtitles_enabled=subtitles_enabled,
        detail=detail,
        cache=cache
    )
    if success:
        processed_files.add(abs_path)
        save_cache(cache)

    return success

# -----------------------------
# Main processing
# -----------------------------
def main():
    total = 0
    all_files = []
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except:
            continue
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

    def _trigger(self):
        if self.timer and self.timer.is_alive():
            self.timer.cancel()
        self.timer = threading.Timer(self.debounce, main)
        self.timer.start()

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".nfo"):
            if detail:
                print(f"[WATCHDOG] Detected new NFO: {event.src_path}")
            self._trigger()

    def on_modified(self, event):
        if not event.is_directory and event.src_path.lower().endswith(".nfo"):
            if detail:
                print(f"[WATCHDOG] Detected modified NFO: {event.src_path}")
            self._trigger()

# -----------------------------
# Execute
# -----------------------------
if __name__ == "__main__":
    main()
    if watch_folders_enabled:
        observer = Observer()
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except:
                continue
            for path in getattr(section, "locations", []):
                observer.schedule(NFOHandler(debounce=watch_debounce_delay), path, recursive=True)
                if detail:
                    print(f"[WATCHDOG] Watching folder: {path}")
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
