#!/usr/bin/env python3
import os, sys, json, time, threading, subprocess, shutil, hashlib
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

# ==============================
# Argument parsing
# ==============================
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
        "watch_debounce_delay": "Debounce time (sec) before processing events",
        "always_apply_nfo": "True = always apply NFO metadata, False = apply only if changed"
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
    "watch_debounce_delay": 2,
    "always_apply_nfo": True
}

# ==============================
# Directories & Config
# ==============================
BASE_DIR = Path(os.environ.get("BASE_DIR", "/app"))
CONFIG_FILE = Path(args.config)
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

# Logging setup
silent = config.get("silent", False)
detail = config.get("detail", False) and not silent
log_level = logging.INFO if not silent else logging.WARNING
logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

# ==============================
# Global constants
# ==============================
VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
api_semaphore = threading.Semaphore(config.get("max_concurrent_requests", 2))
request_delay = config.get("request_delay", 0.1)
threads = config.get("threads", 4)
subtitles_enabled = config.get("subtitles", False)
always_apply_nfo = config.get("always_apply_nfo", False)
processed_files = set()
watch_debounce_delay = config.get("watch_debounce_delay", 2)
cache_lock = threading.Lock()
log_lock = threading.Lock()

# ==============================
# Cache management
# ==============================
cache = {}
cache_modified = False
if CACHE_FILE.exists():
    with CACHE_FILE.open("r", encoding="utf-8") as f:
        cache = json.load(f)

def save_cache():
    global cache_modified
    if cache_modified:
        with cache_lock:
            with CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=4, ensure_ascii=False)
        cache_modified = False

def update_cache(path, plex_id=None, nfo_hash=None):
    global cache_modified
    path = str(path)
    current = cache.get(path, {})
    updated = False
    if plex_id and current.get("plex_id") != plex_id:
        current["plex_id"] = plex_id
        updated = True
    if nfo_hash and current.get("nfo_hash") != nfo_hash:
        current["nfo_hash"] = nfo_hash
        updated = True
    if updated or path not in cache:
        cache[path] = current
        cache_modified = True

def remove_from_cache(path):
    path = str(path)
    if path in cache:
        del cache[path]
        global cache_modified
        cache_modified = True

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
        print(f"[ERROR] Unsupported architecture: {arch}")
        sys.exit(1)

    sha_url = url + ".sha256"
    remote_sha = None
    try:
        remote_sha = requests.get(sha_url, timeout=10).text.strip().split()[0]
    except Exception as e:
        print(f"[WARN] Failed to fetch FFmpeg SHA: {e}")

    local_sha = FFMPEG_SHA_FILE.read_text().strip() if FFMPEG_SHA_FILE.exists() else None

    if FFMPEG_BIN.exists() and remote_sha == local_sha:
        if detail: print("[INFO] FFmpeg up-to-date")
    else:
        tmp_dir = Path("/tmp/ffmpeg_download")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(f"curl -L {url} | tar -xJ -C {tmp_dir}", shell=True, check=True)
        os.makedirs(FFMPEG_BIN.parent, exist_ok=True)
        ffmpeg_path = next(tmp_dir.glob("**/ffmpeg"), None)
        ffprobe_path = next(tmp_dir.glob("**/ffprobe"), None)
        if ffmpeg_path:
            shutil.move(str(ffmpeg_path), FFMPEG_BIN)
            os.chmod(FFMPEG_BIN, 0o755)
        if ffprobe_path:
            shutil.move(str(ffprobe_path), FFMPEG_BIN.parent / "ffprobe")
            os.chmod(FFMPEG_BIN.parent / "ffprobe", 0o755)
        if remote_sha:
            FFMPEG_SHA_FILE.write_text(remote_sha)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    os.environ["PATH"] = f"{FFMPEG_BIN.parent}:{os.environ.get('PATH','')}"

# ==============================
# Plex connection
# ==============================
class HTTPDebugSession(requests.Session):
    def __init__(self, enable_debug=False):
        super().__init__()
        self.enable_debug = enable_debug
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500,502,503,504])
        self.mount("http://", HTTPAdapter(max_retries=retries))
        self.mount("https://", HTTPAdapter(max_retries=retries))

    def send(self, request, **kwargs):
        if self.enable_debug:
            print(f"[HTTP DEBUG] {request.method} {request.url}")
        return super().send(request, **kwargs)

class PlexServerWithHTTPDebug(PlexServer):
    def __init__(self, baseurl, token, debug_http=False):
        super().__init__(baseurl, token)
        self._debug_session = HTTPDebugSession(enable_debug=debug_http)

    def _request(self, path, method="GET", headers=None, params=None, data=None, timeout=None):
        url = self._buildURL(path)
        req_headers = headers or {}
        if self._token:
            req_headers["X-Plex-Token"] = self._token
        resp = self._debug_session.request(method, url, headers=req_headers, params=params, data=data, timeout=timeout)
        resp.raise_for_status()
        return resp

try:
    plex = PlexServerWithHTTPDebug(config["plex_base_url"], config["plex_token"], debug_http=args.debug_http)
except Exception as e:
    logging.error(f"Failed to connect to Plex: {e}")
    sys.exit(1)

# ==============================
# Helper functions
# ==============================
def find_plex_item(abs_path):
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue
        for item in section.all():
            for part in getattr(item, "iterParts", lambda: [])():
                if os.path.abspath(part.file) == abs_path:
                    return item
    return None

def compute_nfo_hash(nfo_path):
    h = hashlib.sha256()
    with open(nfo_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def apply_nfo(ep, file_path):
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title","")
        plot = root.findtext("plot","")
        aired = root.findtext("aired","")

        ep.editTitle(title, locked=True)
        ep.editSortTitle(aired, locked=True)
        ep.editSummary(plot, locked=True)

        # Delete NFO
        try:
            nfo_path.unlink()
        except Exception as e:
            logging.warning(f"Failed to delete NFO: {nfo_path} - {e}")
        return True
    except Exception as e:
        logging.error(f"Error processing {nfo_path}: {e}")
        return False

# ==============================
# Subtitle extraction/upload
# ==============================
LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr","spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}

def map_lang(code):
    return LANG_MAP.get(code.lower(), "und")

def extract_subtitles(video_path):
    base, _ = os.path.splitext(video_path)
    srt_files = []
    ffprobe_cmd = ["ffprobe","-v","error","-select_streams","s",
                   "-show_entries","stream=index:stream_tags=language,codec_name",
                   "-of","json", video_path]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags", {}).get("language", "und"))
            srt = f"{base}.{lang}.srt"
            if os.path.exists(srt):
                continue
            subprocess.run(["ffmpeg","-y","-i",video_path,f"-map","0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(srt):
                srt_files.append((srt, lang))
    except Exception as e:
        print(f"[ERROR] ffprobe/ffmpeg failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep, srt_files):
    for srt, lang in srt_files:
        try:
            with api_semaphore:
                ep.uploadSubtitles(srt, language=lang)
                time.sleep(request_delay)
        except Exception as e:
            print(f"[ERROR] Subtitle upload failed: {srt} - {e}")

# ==============================
# Process single file
# ==============================
def process_file(file_path, ignore_processed=False):
    abs_path = Path(file_path).resolve()
    str_path = str(abs_path)
    if not ignore_processed and str_path in processed_files:
        return False
    if abs_path.suffix.lower() not in VIDEO_EXTS:
        return False

    plex_item = None
    if str_path in cache:
        plex_id = cache[str_path].get("plex_id")
        if plex_id:
            try:
                plex_item = plex.fetchItem(plex_id)
            except Exception:
                plex_item = None
    if not plex_item:
        plex_item = find_plex_item(str_path)
        if plex_item:
            nfo_hash = cache.get(str_path, {}).get("nfo_hash")
            cache[str_path] = {"plex_id": plex_item.key, "nfo_hash": nfo_hash}

    nfo_path = abs_path.with_suffix(".nfo")
    if nfo_path.exists() and nfo_path.stat().st_size > 0 and plex_item:
        nfo_hash = compute_nfo_hash(nfo_path)
        cached_hash = cache.get(str_path, {}).get("nfo_hash")
        if always_apply_nfo or nfo_hash != cached_hash:
            if detail: print(f"[INFO] Applying NFO: {str_path}")
            apply_nfo(plex_item, str_path)
            cache[str_path]["nfo_hash"] = nfo_hash

    if subtitles_enabled and plex_item:
        srt_files = extract_subtitles(str_path)
        if srt_files:
            upload_subtitles(plex_item, srt_files)

    processed_files.add(str_path)
    return True

# ==============================
# Watchdog
# ==============================
class VideoEventHandler(FileSystemEventHandler):
    def __init__(self):
        self.nfo_queue = set()
        self.video_queue = set()
        self.lock = threading.Lock()
        self.nfo_timer = None
        self.video_timer = None

    def on_any_event(self, event):
        if event.is_directory: return
        path = os.path.abspath(event.src_path)
        ext = os.path.splitext(path)[1].lower()
        with self.lock:
            if event.event_type == "deleted" and ext in VIDEO_EXTS:
                remove_from_cache(path)
                save_cache()
            elif event.event_type == "created":
                if ext in VIDEO_EXTS:
                    plex_item = find_plex_item(path)
                    if plex_item:
                        update_cache(path, plex_item.key)
                    self.schedule_video(path)
                elif ext == ".nfo":
                    self.schedule_nfo(path)

    def schedule_nfo(self, path):
        self.nfo_queue.add(path)
        if not self.nfo_timer:
            self.nfo_timer = threading.Timer(watch_debounce_delay, self.process_nfo_queue)
            self.nfo_timer.start()

    def schedule_video(self, path):
        self.video_queue.add(path)
        if not self.video_timer:
            self.video_timer = threading.Timer(watch_debounce_delay, self.process_video_queue)
            self.video_timer.start()

    def process_nfo_queue(self):
        with self.lock:
            queue = list(self.nfo_queue)
            self.nfo_queue.clear()
            self.nfo_timer = None
        for nfo_path in queue:
            video_path = str(Path(nfo_path).with_suffix(".mkv"))  # 기본 확장자 체크
            process_file(video_path, ignore_processed=True)
        save_cache()

    def process_video_queue(self):
        with self.lock:
            queue = list(self.video_queue)
            self.video_queue.clear()
            self.video_timer = None
        for video_path in queue:
            process_file(video_path, ignore_processed=True)
        save_cache()

# ==============================
# Main
# ==============================
def main():
    setup_ffmpeg()
    # Initial scan
    all_videos = []
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue
        for loc in getattr(section, "locations", []):
            for root, dirs, files in os.walk(loc):
                for f in files:
                    if f.lower().endswith(VIDEO_EXTS):
                        all_videos.append(os.path.abspath(os.path.join(root, f)))

    # ThreadPoolExecutor
    if threads > 1:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(process_file, f): f for f in all_videos}
            for fut in as_completed(futures):
                _ = fut.result()
    else:
        for f in all_videos:
            process_file(f)

    save_cache()

    # Watchdog
    if config.get("watch_folders", False) and not DISABLE_WATCHDOG:
        event_handler = VideoEventHandler()
        observer = Observer()
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except:
                continue
            for path in getattr(section, "locations", []):
                observer.schedule(event_handler, path, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__ == "__main__":
    main()
