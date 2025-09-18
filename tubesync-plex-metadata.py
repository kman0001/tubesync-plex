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
log_level = logging.INFO if not silent else logging.WARNING
logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

# ==============================
# HTTP Debug session
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
# PlexServer wrapper
# ==============================
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

# ==============================
# Plex connection
# ==============================
try:
    plex = PlexServerWithHTTPDebug(
        config["plex_base_url"], 
        config["plex_token"], 
        debug_http=args.debug_http
    )
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
# Cache management update (store Plex ID + NFO hash)
# ==============================
def update_cache(path, plex_id=None, nfo_hash=None):
    """
    Update cache for a video file.
    Stores Plex ID and NFO hash together.
    """
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

    local_sha = None
    if FFMPEG_SHA_FILE.exists():
        local_sha = FFMPEG_SHA_FILE.read_text().strip()

    if FFMPEG_BIN.exists() and remote_sha == local_sha:
        if detail: print("[INFO] FFmpeg up-to-date")
    else:
        tmp_dir = Path("/tmp/ffmpeg_download")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(f"curl -L {url} | tar -xJ -C {tmp_dir}", shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Failed download/extract FFmpeg: {e}")
            if not FFMPEG_BIN.exists():
                sys.exit(1)

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
# Plex item finder
# ==============================
def find_plex_item(abs_path):
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
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
                    if f.lower().endswith(VIDEO_EXTS):
                        all_files.append(os.path.abspath(os.path.join(root,f)))

    for f in all_files:
        if f not in cache:
            plex_item = find_plex_item(f)
            if plex_item:
                cache[f] = plex_item.key

    removed = existing_files - set(all_files)
    for f in removed:
        cache.pop(f, None)

# ==============================
# Subtitle extraction & upload
# ==============================
LANG_MAP = {
    "eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr",
    "spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"
}

def map_lang(code):
    return LANG_MAP.get(code.lower(), "und")

def extract_subtitles(video_path):
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
            if detail:
                print(f"[SUBTITLE] Uploaded: {srt}")
        except Exception as e:
            print(f"[ERROR] Subtitle upload failed: {srt} - {e}")

# ==============================
# NFO processing with hash
# ==============================
import hashlib

def compute_nfo_hash(nfo_path):
    """Compute SHA256 hash of the NFO file."""
    h = hashlib.sha256()
    with open(nfo_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def apply_nfo(ep, file_path):
    """Apply NFO metadata if changed based on hash, then delete NFO."""
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False
    global cache
    nfo_hash = compute_nfo_hash(nfo_path)
    cached_hash = cache.get(file_path, {}).get("nfo_hash")
    if cached_hash == nfo_hash:
        if detail:
            print(f"[DEBUG] NFO hash unchanged, skipping: {nfo_path}")
        return False  # Skip if hash unchanged

    # Parse and apply metadata
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title","")
        plot = root.findtext("plot","")
        aired = root.findtext("aired","")

        ep.editTitle(title, locked=True)
        ep.editSortTitle(aired, locked=True)
        ep.editSummary(plot, locked=True)

        # Update cache with new nfo hash
        cache[file_path] = {"plex_id": ep.key, "nfo_hash": nfo_hash}

        # Delete NFO after processing
        try:
            nfo_path.unlink()
            if detail:
                print(f"[DEBUG] Deleted NFO: {nfo_path}")
        except Exception as e:
            logging.warning(f"Failed to delete NFO: {nfo_path} - {e}")
        return True
    except Exception as e:
        logging.error(f"Error processing {nfo_path}: {e}")
        return False

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

    global cache
    plex_item = None
    if str_path in cache:
        plex_id = cache[str_path].get("plex_id")
        if plex_id:
            try:
                plex_item = plex.fetchItem(plex_id)
            except Exception as e:
                if detail:
                    logging.warning(f"Failed to fetch Plex item {plex_id}: {e}")
                plex_item = None

    if not plex_item:
        plex_item = find_plex_item(str_path)
        if plex_item:
            # Update cache with Plex ID but keep existing nfo_hash if present
            nfo_hash = cache.get(str_path, {}).get("nfo_hash")
            cache[str_path] = {"plex_id": plex_item.key, "nfo_hash": nfo_hash}

    success = False
    nfo_path = abs_path.with_suffix(".nfo")
    if nfo_path.exists() and nfo_path.stat().st_size > 0 and plex_item:
        if not config.get("silent", False):
            print(f"[INFO] Applying NFO: {abs_path}")
        if apply_nfo(plex_item, str_path):
            success = True

    processed_files.add(str_path)
    return success

# ==============================
# Watchdog event handler (final version)
# ==============================
class VideoEventHandler(FileSystemEventHandler):
    def __init__(self):
        self.nfo_queue = set()
        self.video_queue = set()
        self.lock = threading.Lock()
        self.nfo_timer = None
        self.video_timer = None
        self.retry_queue = {}

    def on_any_event(self, event):
        if event.is_directory:
            return
        path = os.path.abspath(event.src_path)
        ext = os.path.splitext(path)[1].lower()

        with self.lock:
            # ==============================
            # Video file deleted
            # Remove Plex ID and NFO hash from cache
            # ==============================
            if event.event_type == "deleted" and ext in VIDEO_EXTS:
                remove_from_cache(path)  # removes both Plex ID and NFO hash
                save_cache()

            # ==============================
            # New video or NFO file created
            # ==============================
            elif event.event_type == "created":
                # Video created
                if ext in VIDEO_EXTS:
                    if path not in cache:
                        plex_item = find_plex_item(path)
                        if plex_item:
                            update_cache(path, plex_item.key)
                        save_cache()
                    self.schedule_video(path)

                # NFO created
                elif ext == ".nfo":
                    self.schedule_nfo(path)

    # ==============================
    # Schedule NFO processing
    # ==============================
    def schedule_nfo(self, path):
        self.nfo_queue.add(path)
        if not self.nfo_timer:
            self.nfo_timer = threading.Timer(watch_debounce_delay, self.process_nfo_queue)
            self.nfo_timer.start()

    # ==============================
    # Schedule Video processing
    # ==============================
    def schedule_video(self, path):
        self.video_queue.add(path)
        if not self.video_timer:
            self.video_timer = threading.Timer(watch_debounce_delay, self.process_video_queue)
            self.video_timer.start()

    # ==============================
    # Process queued NFO files
    # ==============================
    def process_nfo_queue(self):
        with self.lock:
            queue = list(self.nfo_queue)
            self.nfo_queue.clear()
            self.nfo_timer = None

        for nfo_path in queue:
            video_path = self._find_video(nfo_path)
            if video_path:
                # Compute hash of NFO
                nfo_hash = compute_hash(nfo_path)
                cached_hash = cache.get(video_path, {}).get("nfo_hash")

                # ==============================
                # If NFO hash differs or not cached -> apply metadata
                # ==============================
                if nfo_hash != cached_hash:
                    plex_item = find_plex_item(video_path)
                    if plex_item:
                        apply_nfo(plex_item, video_path)
                        update_cache(video_path, plex_item.key, nfo_hash)
                
                # ==============================
                # Delete NFO after processing
                # ==============================
                try:
                    Path(nfo_path).unlink()
                except Exception as e:
                    logging.warning(f"Failed to delete NFO: {nfo_path} - {e}")

        self._process_retry()

    # ==============================
    # Process queued video files
    # ==============================
    def process_video_queue(self):
        with self.lock:
            queue = list(self.video_queue)
            self.video_queue.clear()
            self.video_timer = None

        for video_path in queue:
            process_file(video_path, ignore_processed=True)
        save_cache()

    # ==============================
    # Find video file matching NFO
    # ==============================
    def _find_video(self, nfo_path):
        for ext in VIDEO_EXTS:
            candidate = str(Path(nfo_path).with_suffix(ext))
            if os.path.exists(candidate):
                return candidate
        return None

    # ==============================
    # Retry mechanism for NFO processing failures
    # ==============================
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

# ==============================
# Main entry
# ==============================
def main():
    setup_ffmpeg()
    scan_and_update_cache()
    save_cache()

    # Initial scan using ThreadPoolExecutor
    all_videos = list(cache.keys())
    if threads > 1:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(process_file, f): f for f in all_videos}
            for fut in as_completed(futures):
                _ = fut.result()
    else:
        for f in all_videos:
            process_file(f)

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
