#!/usr/bin/env python3
import os, sys, json, time, threading, subprocess, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from plexapi.server import PlexServer
import lxml.etree as ET
import argparse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import platform
import requests
import logging

# ==============================
# Argument parsing
# ==============================
parser = argparse.ArgumentParser(description="TubeSync Plex Metadata Sync")
parser.add_argument("--disable-watchdog", action="store_true", help="Disable folder watching")
parser.add_argument("--config", type=str, default=None, help="Path to config.json")
args = parser.parse_args()
DISABLE_WATCHDOG = args.disable_watchdog

# ==============================
# Default config
# ==============================
default_config = {
    "_comment": {
        "plex_base_url": "Base URL of your Plex server (e.g., http://localhost:32400).",
        "plex_token": "Your Plex authentication token.",
        "plex_library_ids": "List of Plex library IDs to sync (e.g., [10,21,35]).",
        "silent": "true = only summary logs, false = detailed logs",
        "detail": "true = verbose mode (debug output)",
        "subtitles": "true = extract and upload subtitles",
        "threads": "Number of worker threads for initial scanning",
        "max_concurrent_requests": "Max concurrent Plex API requests",
        "request_delay": "Delay between Plex API requests (sec)",
        "watch_folders": "true = enable real-time folder monitoring",
        "watch_debounce_delay": "Debounce time (sec) before processing events"
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

# ==============================
# Directories & Config
# ==============================
BASE_DIR = Path(os.environ.get("BASE_DIR", "/app"))
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = Path(args.config) if args.config else CONFIG_DIR / "config.json"
CACHE_FILE = CONFIG_FILE.parent / "tubesync_cache.json"
FFMPEG_BIN = BASE_DIR / "ffmpeg"           # venv 내부가 아닌 앱 내부 전용 설치
FFMPEG_SHA_FILE = BASE_DIR / ".ffmpeg_sha"

# Load or create config
if not CONFIG_FILE.exists():
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

with CONFIG_FILE.open("r", encoding="utf-8") as f:
    config = json.load(f)

if DISABLE_WATCHDOG:
    config["watch_folders"] = False

# ==============================
# Logging setup
# ==============================
silent = config.get("silent", False)
detail = config.get("detail", False) and not silent  # silent=True면 detail 무시

log_level = logging.DEBUG if detail else (logging.INFO if not silent else logging.WARNING)
logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

# ==============================
# Plex connection
# ==============================
try:
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
except Exception as e:
    logging.error(f"Failed to connect to Plex: {e}")
    sys.exit(1)

# ==============================
# Globals
# ==============================
VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
api_semaphore = threading.Semaphore(config.get("max_concurrent_requests", 2))
request_delay = config.get("request_delay", 0.1)
threads = config.get("threads", 4)
subtitles_enabled = config.get("subtitles", False)
processed_files = set()
watch_debounce_delay = config.get("watch_debounce_delay", 2)
cache_lock = threading.Lock()
log_lock = threading.Lock()

# ==============================
# Cache
# ==============================
if CACHE_FILE.exists():
    with CACHE_FILE.open("r", encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    logging.debug(f"Created empty cache at {CACHE_FILE}")

def save_cache():
    with cache_lock:
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            logging.debug(f"Saved cache to {CACHE_FILE}, total items: {len(cache)}")
        except Exception as e:
            logging.error(f"Failed to save cache: {e}")

# ==============================
# FFmpeg setup
# ==============================
def setup_ffmpeg():
    arch = platform.machine()
    if arch == "x86_64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif arch == "aarch64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else:
        logging.error(f"Unsupported architecture: {arch}")
        sys.exit(1)

    sha_url = url + ".sha256"
    remote_sha = None
    try:
        remote_sha = requests.get(sha_url, timeout=5).text.strip().split()[0]
    except Exception as e:
        logging.warning(f"Failed to fetch remote SHA: {e}")

    local_sha = FFMPEG_SHA_FILE.read_text().strip() if FFMPEG_SHA_FILE.exists() else None

    # 네트워크 오류나 SHA 미일치 시만 설치
    if not FFMPEG_BIN.exists() or (remote_sha and remote_sha != local_sha):
        logging.info("Downloading/updating static FFmpeg...")
        tmp_dir = Path("/tmp/ffmpeg_download")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(f"curl -fL {url} | tar -xJ --strip-components=1 -C {tmp_dir} ffmpeg", 
                           shell=True, check=True)
            shutil.move(str(tmp_dir / "ffmpeg"), FFMPEG_BIN)
            FFMPEG_BIN.chmod(0o755)
            if remote_sha:
                FFMPEG_SHA_FILE.write_text(remote_sha)
        except subprocess.CalledProcessError as e:
            logging.error(f"FFmpeg download/extract failed: {e}")
            if FFMPEG_BIN.exists():
                logging.info("Using existing local FFmpeg binary")
            else:
                sys.exit(1)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    os.environ["PATH"] = f"{FFMPEG_BIN.parent}:{os.environ.get('PATH','')}"

setup_ffmpeg()

# -----------------------------
# Plex item finder
# -----------------------------
def find_plex_item(abs_path):
    """Find Plex item by absolute path across libraries"""
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except:
            continue
        for item in section.all():
            for part in item.iterParts():
                if os.path.abspath(part.file) == abs_path:
                    return item
    return None

# -----------------------------
# Library scan & cache update
# -----------------------------
def scan_and_update_cache():
    """Full Plex library scan to update cache"""
    global cache
    existing_files = set(cache.keys())
    all_files = []

    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except:
            continue
        for p in getattr(section, "locations", []):
            for root, dirs, files in os.walk(p):
                for f in files:
                    all_files.append(os.path.join(root, f))

    current_files = set()
    for f in all_files:
        abs_path = os.path.abspath(f)
        if not f.lower().endswith(VIDEO_EXTS):
            continue
        current_files.add(abs_path)
        if abs_path not in cache:
            plex_item = find_plex_item(abs_path)
            if plex_item:
                cache[abs_path] = plex_item.key

    removed = existing_files - current_files
    for f in removed:
        cache.pop(f, None)

# -----------------------------
# Subtitles
# -----------------------------
LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr","spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}
def map_lang(code): 
    return LANG_MAP.get(code.lower(),"und")

def extract_subtitles(video_path):
    """
    Extract embedded subtitles from video into .srt files.
    detail=True이면 ffprobe/ffmpeg stderr 출력
    """
    base,_ = os.path.splitext(video_path)
    srt_files = []
    ffprobe_cmd = [str(FFMPEG_BIN.parent / "ffprobe"), "-v", "error", "-select_streams", "s",
                   "-show_entries", "stream=index:stream_tags=language,codec_name",
                   "-of", "json", str(video_path)]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags", {}).get("language","und"))
            srt = f"{base}.{lang}.srt"
            if Path(srt).exists(): 
                continue
            ffmpeg_cmd = [str(FFMPEG_BIN), "-y", "-i", str(video_path), f"-map", f"0:s:{idx}", srt]
            try:
                if detail:
                    subprocess.run(ffmpeg_cmd, check=True)
                else:
                    subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                if Path(srt).exists(): 
                    srt_files.append((srt, lang))
            except subprocess.CalledProcessError as e:
                logging.error(f"ffmpeg extraction failed for {video_path} stream {idx}: {e}")
    except Exception as e:
        logging.error(f"ffprobe failed for {video_path}: {e}")
    return srt_files

def upload_subtitles(ep, srt_files):
    """
    Upload extracted subtitles to Plex episode object.
    Uses semaphore and request_delay to avoid rate limits.
    """
    for srt, lang in srt_files:
        try:
            with api_semaphore:
                ep.uploadSubtitles(srt, language=lang)
                time.sleep(request_delay)
            logging.info(f"Uploaded subtitle: {srt}")
        except Exception as e:
            logging.error(f"Subtitle upload failed: {srt} - {e}")

# -----------------------------
# NFO processing
# -----------------------------
def apply_nfo(ep, file_path):
    """Apply NFO metadata to Plex item"""
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title", "")
        plot = root.findtext("plot", "")
        aired = root.findtext("aired", "")

        ep.editTitle(title, locked=True)
        ep.editSortTitle(aired, locked=True)
        ep.editSummary(plot, locked=True)

        if subtitles_enabled:
            srt_files = extract_subtitles(file_path)
            if srt_files:
                upload_subtitles(ep, srt_files)

        try:
            nfo_path.unlink()
            if detail:
                print(f"[-] Deleted NFO: {nfo_path}")
        except Exception as e:
            print(f"[WARN] Failed to delete NFO file: {nfo_path} - {e}")

        return True
    except Exception as e:
        print(f"[!] Error processing {nfo_path}: {e}")
        return False

# -----------------------------
# Process single file with NFO & subtitles
# -----------------------------
def process_file(file_path, ignore_processed=False):
    """
    Process a single video file:
    - Apply NFO if exists
    - Extract & upload subtitles if enabled
    - Respect silent/detail flags
    """
    abs_path = Path(file_path).resolve()
    if not ignore_processed and abs_path in processed_files:
        return False
    if not abs_path.suffix.lower() in VIDEO_EXTS:
        return False

    plex_item = None
    key = cache.get(str(abs_path))
    if key:
        try:
            plex_item = plex.fetchItem(key)
        except Exception as e:
            if detail:
                logging.warning(f"Failed to fetch Plex item {key}: {e}")
            plex_item = None

    if not plex_item:
        plex_item = find_plex_item(str(abs_path))
        if plex_item:
            cache[str(abs_path)] = plex_item.key

    nfo_path = abs_path.with_suffix(".nfo")
    success = False

    if nfo_path.exists() and nfo_path.stat().st_size > 0 and plex_item:
        try:
            tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
            root = tree.getroot()
            title = root.findtext("title","")
            plot = root.findtext("plot","")
            aired = root.findtext("aired","")

            if not config.get("silent", False):
                print(f"[INFO] Applying NFO: {abs_path} -> {title}")

            plex_item.editTitle(title, locked=True)
            plex_item.editSortTitle(aired, locked=True)
            plex_item.editSummary(plot, locked=True)

            # subtitles
            if subtitles_enabled:
                srt_files = extract_subtitles(str(abs_path))
                if srt_files:
                    upload_subtitles(plex_item, srt_files)

            try:
                nfo_path.unlink()
                if detail:
                    print(f"[DEBUG] Deleted NFO file: {nfo_path}")
            except Exception as e:
                logging.warning(f"Failed to delete NFO: {nfo_path} - {e}")

            success = True
        except Exception as e:
            logging.error(f"NFO processing error for {nfo_path}: {e}")

    processed_files.add(abs_path)
    return success

# -----------------------------
# Watchdog event handler
# -----------------------------
class VideoEventHandler(FileSystemEventHandler):
    """Handles create/delete events for video & NFO files with debounce"""

    def __init__(self):
        self.nfo_queue = set()
        self.video_queue = set()
        self.lock = threading.Lock()
        self.nfo_timer = None
        self.video_timer = None
        self.retry_queue = {}  # {path: (timestamp, count)}

    def on_any_event(self, event):
        if event.is_directory:
            return
        path = os.path.abspath(event.src_path)
        ext = os.path.splitext(path)[1].lower()
        with self.lock:
            if event.event_type == "deleted" and ext in VIDEO_EXTS:
                cache.pop(path, None)
                save_cache()
            elif event.event_type == "created" and ext in VIDEO_EXTS:
                if path not in cache:
                    plex_item = find_plex_item(path)
                    if plex_item:
                        cache[path] = plex_item.key
                    save_cache()
                self.schedule_video(path)
            elif ext == ".nfo":
                self.schedule_nfo(path)

    def schedule_nfo(self, path):
        self.nfo_queue.add(path)
        if not self.nfo_timer:
            self.nfo_timer = threading.Timer(10, self.process_nfo_queue)
            self.nfo_timer.start()

    def schedule_video(self, path):
        self.video_queue.add(path)
        if not self.video_timer:
            self.video_timer = threading.Timer(2, self.process_video_queue)
            self.video_timer.start()

    def process_nfo_queue(self):
        with self.lock:
            queue = list(self.nfo_queue)
            self.nfo_queue.clear()
            self.nfo_timer = None
        for nfo_path in queue:
            video_path = self._find_video(nfo_path)
            if video_path:
                process_file(video_path, ignore_processed=True)
        self._process_retry()

    def process_video_queue(self):
        with self.lock:
            queue = list(self.video_queue)
            self.video_queue.clear()
            self.video_timer = None
        for video_path in queue:
            process_file(video_path, ignore_processed=True)
        save_cache()

    def _find_video(self, nfo_path):
        for ext in VIDEO_EXTS:
            candidate = str(Path(nfo_path).with_suffix(ext))
            if os.path.exists(candidate):
                return candidate
        return None

    def _process_retry(self):
        now = time.time()
        for path, (retry_time, count) in list(self.retry_queue.items()):
            if now >= retry_time:
                if process_file(path, ignore_processed=True):
                    del self.retry_queue[path]
                elif count < 3:
                    self.retry_queue[path] = (now + 5, count + 1)
                else:
                    print(f"[WARN] NFO failed 3x: {path}")
                    del self.retry_queue[path]

# -----------------------------
# Main entry point
# -----------------------------
def main():
    scan_and_update_cache()
    save_cache()

    total = 0
    with ThreadPoolExecutor(max_workers=threads) as ex:
        futures = {ex.submit(process_file, f): f for f in cache.keys()}
        for fut in as_completed(futures):
            if fut.result():
                total += 1

    if not config.get("silent", False):
        print(f"[INFO] Total items updated: {total}")

    save_cache()

    if config.get("watch_folders", False) and not DISABLE_WATCHDOG:
        observer = Observer()
        handler = VideoEventHandler()
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except:
                continue
            for p in getattr(section, "locations", []):
                observer.schedule(handler, p, recursive=True)

        observer.start()
        print("[INFO] Watchdog started. Monitoring file changes...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__ == "__main__":
    main()
