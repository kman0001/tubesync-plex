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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------
# Argument parsing
# --------------------------
parser = argparse.ArgumentParser(description="TubeSync Plex Metadata")
parser.add_argument("--config", required=True, help="Path to config file")
parser.add_argument("--disable-watchdog", action="store_true", help="Disable folder watchdog")
parser.add_argument("--detail", action="store_true", help="Enable detailed logging")
parser.add_argument("--debug-http", action="store_true", help="Enable HTTP debug logging")
args = parser.parse_args()
DISABLE_WATCHDOG = args.disable_watchdog

# ==============================
# Default config
# ==============================
default_config = {
    "_comment": { ... },  # same as before
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
FFMPEG_BIN = BASE_DIR / "ffmpeg"
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
detail = config.get("detail", False) and not silent

# 기본 로그는 INFO 수준
log_level = logging.INFO if not silent else logging.WARNING
logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

# ==============================
# HTTP Debug session
# ==============================
class HTTPDebugSession(requests.Session):
    """Requests session that logs all HTTP requests/responses only if enable_debug=True"""
    def __init__(self, enable_debug=False):
        super().__init__()
        self.enable_debug = enable_debug
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500,502,503,504])
        self.mount("http://", HTTPAdapter(max_retries=retries))
        self.mount("https://", HTTPAdapter(max_retries=retries))

    def send(self, request, **kwargs):
        if self.enable_debug:
            print("[HTTP DEBUG] ────── REQUEST ──────")
            print(f"Method: {request.method}\nURL: {request.url}\nHeaders:\n  " +
                  "\n  ".join(f"{k}: {v}" for k,v in request.headers.items()))
            if request.body:
                print(f"Body: {request.body}")
        response = super().send(request, **kwargs)
        if self.enable_debug:
            print("[HTTP DEBUG] ────── RESPONSE ──────")
            print(f"Status Code: {response.status_code} {response.reason}")
            print(f"Headers:\n  " + "\n  ".join(f"{k}: {v}" for k,v in response.headers.items()))
            print(f"Body (truncated): {response.text[:1000]}")
            print(f"Elapsed Time: {response.elapsed.total_seconds():.3f}s\n")
        return response

# ==============================
# PlexServer with HTTP debug
# ==============================
class PlexServerWithHTTPDebug(PlexServer):
    def _request(self, path, method="GET", headers=None, params=None, data=None, timeout=None):
        if not hasattr(self, "_debug_session"):
            self._debug_session = HTTPDebugSession(enable_debug=args.debug_http)
        url = self._buildURL(path)
        req_headers = headers or {}
        if self._token:
            req_headers["X-Plex-Token"] = self._token
        resp = self._debug_session.request(method, url, headers=req_headers, params=params, data=data, timeout=timeout)
        resp.raise_for_status()
        return resp

# ==============================
# Plex connection
# ==============================
try:
    plex = PlexServerWithHTTPDebug(config["plex_base_url"], config["plex_token"])
except Exception as e:
    logging.error(f"Failed to connect to Plex: {e}")
    sys.exit(1)

# ==============================
# Global constants
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
    """Save cache to disk safely with lock"""
    with cache_lock:
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            logging.debug(f"Saved cache to {CACHE_FILE}, total items: {len(cache)}")
        except Exception as e:
            logging.error(f"Failed to save cache: {e}")

# ==============================
# FFmpeg + FFprobe setup
# ==============================
def setup_ffmpeg():
    """Setup static FFmpeg/FFprobe for the system architecture"""
    arch = platform.machine()
    if arch == "x86_64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif arch == "aarch64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else:
        print(f"[ERROR] Unsupported architecture: {arch}")
        sys.exit(1)

    sha_url = url + ".sha256"
    remote_sha = None
    try:
        remote_sha = requests.get(sha_url, timeout=10).text.strip().split()[0]
    except Exception as e:
        print(f"[WARN] Failed to fetch FFmpeg SHA: {e}")

    local_sha = None
    if os.path.exists(FFMPEG_SHA_FILE):
        with open(FFMPEG_SHA_FILE, "r") as f:
            local_sha = f.read().strip()

    # Skip download if up-to-date
    if os.path.exists(FFMPEG_BIN) and remote_sha and remote_sha == local_sha:
        if detail: print("[INFO] Static FFmpeg/FFprobe up-to-date, skipping download.")
    else:
        if os.path.exists(FFMPEG_BIN) and not remote_sha:
            if detail: print("[WARN] Network error fetching SHA, using existing FFmpeg/FFprobe.")
        else:
            with log_lock: print("[INFO] Downloading/updating static FFmpeg and FFprobe...")
            tmp_dir = Path("/tmp/ffmpeg_download")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            tmp_dir.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(f"curl -L {url} | tar -xJ -C {tmp_dir}", 
                               shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Failed to download/extract FFmpeg: {e}")
                if os.path.exists(FFMPEG_BIN):
                    print("[WARN] Using existing FFmpeg/FFprobe despite download failure.")
                    return
                else:
                    sys.exit(1)

            os.makedirs(os.path.dirname(FFMPEG_BIN), exist_ok=True)

            # Move ffmpeg
            ffmpeg_path = next(tmp_dir.glob("**/ffmpeg"), None)
            if ffmpeg_path:
                shutil.move(str(ffmpeg_path), FFMPEG_BIN)
                os.chmod(FFMPEG_BIN, 0o755)
            else:
                print("[ERROR] ffmpeg binary not found in downloaded archive.")
                sys.exit(1)

            # Move ffprobe
            ffprobe_path = next(tmp_dir.glob("**/ffprobe"), None)
            if ffprobe_path:
                shutil.move(str(ffprobe_path), FFMPEG_BIN.parent / "ffprobe")
                os.chmod(str(FFMPEG_BIN.parent / "ffprobe"), 0o755)
            elif detail:
                print("[WARN] ffprobe binary not found, only ffmpeg installed.")

            if remote_sha:
                with open(FFMPEG_SHA_FILE, "w") as f:
                    f.write(remote_sha)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    os.environ["PATH"] = f"{os.path.dirname(FFMPEG_BIN)}:{os.environ.get('PATH','')}"

# ==============================
# Plex item finder
# ==============================
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

# ==============================
# Library scan & cache update
# ==============================
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
LANG_MAP = {
    "eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr",
    "spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"
}

def map_lang(code):
    """Map FFmpeg language codes to standardized 2-letter codes"""
    return LANG_MAP.get(code.lower(), "und")

def extract_subtitles(video_path):
    """Extract subtitle streams from a video file using ffprobe + ffmpeg"""
    base, _ = os.path.splitext(video_path)
    srt_files = []
    ffprobe_cmd = [
        "ffprobe","-v","error","-select_streams","s",
        "-show_entries","stream=index:stream_tags=language,codec_name",
        "-of","json", video_path
    ]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags", {}).get("language", "und"))
            srt = f"{base}.{lang}.srt"
            if os.path.exists(srt):
                continue
            subprocess.run(
                ["ffmpeg","-y","-i",video_path,f"-map","0:s:{idx}",srt],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            if os.path.exists(srt):
                srt_files.append((srt, lang))
    except Exception as e:
        print(f"[ERROR] ffprobe/ffmpeg failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep, srt_files):
    """Upload extracted subtitles to Plex respecting concurrency and logging"""
    for srt, lang in srt_files:
        try:
            with api_semaphore:
                ep.uploadSubtitles(srt, language=lang)
                time.sleep(request_delay)
            if detail:
                print(f"[SUBTITLE] Uploaded: {srt}")
        except Exception as e:
            print(f"[ERROR] Subtitle upload failed: {srt} - {e}")

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
# Process single file
# -----------------------------
def process_file(file_path, ignore_processed=False):
    """Process video file: apply NFO and upload subtitles"""
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
    """Handle create/delete events for video & NFO files with debounce"""

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
        """Add NFO file to queue with debounce"""
        self.nfo_queue.add(path)
        if not self.nfo_timer:
            self.nfo_timer = threading.Timer(10, self.process_nfo_queue)
            self.nfo_timer.start()

    def schedule_video(self, path):
        """Add video file to queue with debounce"""
        self.video_queue.add(path)
        if not self.video_timer:
            self.video_timer = threading.Timer(2, self.process_video_queue)
            self.video_timer.start()

    def process_nfo_queue(self):
        """Process queued NFO files"""
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
        """Process queued video files"""
        with self.lock:
            queue = list(self.video_queue)
            self.video_queue.clear()
            self.video_timer = None
        for video_path in queue:
            process_file(video_path, ignore_processed=True)
        save_cache()

    def _find_video(self, nfo_path):
        """Find corresponding video file for NFO"""
        for ext in VIDEO_EXTS:
            candidate = str(Path(nfo_path).with_suffix(ext))
            if os.path.exists(candidate):
                return candidate
        return None

    def _process_retry(self):
        """Retry failed NFO processes up to 3 times"""
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
    """Main execution: scan libraries, process files, optionally watch folders"""
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

    if config.get("watch_folders", False) and not args.disable_watchdog:
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
