#!/usr/bin/env python3
import os, sys, json, time, threading, subprocess, shutil, hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from plexapi.server import PlexServer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import platform
import requests
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import lxml.etree as ET

# ==============================
# Arguments
# ==============================
import argparse
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
        "silent": "True = only summary logs, False = detailed logs",
        "detail": "True = verbose mode (debug output)",
        "subtitles": "True = extract and upload subtitles",
        "always_apply_nfo": "True = always apply NFO metadata regardless of hash",
        "threads": "Number of worker threads for initial scanning",
        "max_concurrent_requests": "Max concurrent Plex API requests",
        "request_delay": "Delay between Plex API requests (sec)",
        "watch_folders": "True = enable real-time folder monitoring",
        "watch_debounce_delay": "Debounce time (sec) before processing events"
    },
    "plex_base_url": "",
    "plex_token": "",
    "plex_library_ids": [],
    "silent": False,
    "detail": False,
    "subtitles": False,
    "always_apply_nfo": True,
    "threads": 8,
    "max_concurrent_requests": 4,
    "request_delay": 0.2,
    "watch_folders": True,
    "watch_debounce_delay": 3
}

BASE_DIR = Path(os.environ.get("BASE_DIR", "/app"))
CONFIG_FILE = Path(args.config)
CACHE_FILE = CONFIG_FILE.parent / "tubesync_cache.json"
FFMPEG_BIN = BASE_DIR / "ffmpeg"
FFMPEG_SHA_FILE = BASE_DIR / ".ffmpeg_sha"

# ==============================
# Load config
# ==============================
if not CONFIG_FILE.exists():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

with CONFIG_FILE.open("r", encoding="utf-8") as f:
    config = json.load(f)

if DISABLE_WATCHDOG:
    config["watch_folders"] = False

# ==============================
# Logging
# ==============================
silent = config.get("silent", False)
detail = config.get("detail", False) and not silent
log_level = logging.INFO if not silent else logging.WARNING
logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

# ==============================
# HTTP debug session
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
            print("[HTTP DEBUG] REQUEST:", request.method, request.url)
        response = super().send(request, **kwargs)
        if self.enable_debug:
            print("[HTTP DEBUG] RESPONSE:", response.status_code, response.reason)
        return response

# ==============================
# Plex server wrapper
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
# Connect Plex
# ==============================
try:
    plex = PlexServerWithHTTPDebug(config["plex_base_url"], config["plex_token"], debug_http=args.debug_http)
except Exception as e:
    logging.error(f"Failed to connect to Plex: {e}")
    sys.exit(1)

# ==============================
# Globals
# ==============================
VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
cache_lock = threading.Lock()
api_semaphore = threading.Semaphore(config.get("max_concurrent_requests", 2))
request_delay = config.get("request_delay", 0.1)
threads = config.get("threads", 4)
subtitles_enabled = config.get("subtitles", False)
processed_files = set()
watch_debounce_delay = config.get("watch_debounce_delay", 2)
cache_modified = False
pending_events = {}
pending_lock = threading.Lock()

# ==============================
# Load or init cache
# ==============================
if CACHE_FILE.exists():
    with CACHE_FILE.open("r", encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}

def save_cache():
    global cache_modified
    with cache_lock:
        if cache_modified:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            cache_modified = False

def update_cache(path, plex_id=None, nfo_hash=None):
    global cache_modified
    path = str(path)
    with cache_lock:
        current = cache.get(path, {})
        if plex_id: current["plex_id"] = plex_id
        if nfo_hash: current["nfo_hash"] = nfo_hash
        cache[path] = current
        cache_modified = True

def remove_from_cache(path):
    path = str(path)
    with cache_lock:
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
        print(f"[ERROR] Unsupported arch: {arch}")
        sys.exit(1)

    remote_sha = None
    try:
        remote_sha = requests.get(url + ".sha256", timeout=10).text.strip().split()[0]
    except Exception:
        pass

    local_sha = FFMPEG_SHA_FILE.read_text().strip() if FFMPEG_SHA_FILE.exists() else None

    if FFMPEG_BIN.exists() and remote_sha == local_sha:
        if detail: print("[INFO] FFmpeg up-to-date")
        return

    tmp_dir = Path("/tmp/ffmpeg_dl")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(f"curl -L {url} | tar -xJ -C {tmp_dir}", shell=True, check=True)
    ffmpeg_path = next(tmp_dir.glob("**/ffmpeg"))
    ffprobe_path = next(tmp_dir.glob("**/ffprobe"))
    shutil.move(str(ffmpeg_path), FFMPEG_BIN)
    shutil.move(str(ffprobe_path), FFMPEG_BIN.parent / "ffprobe")
    os.chmod(FFMPEG_BIN, 0o755)
    os.chmod(FFMPEG_BIN.parent / "ffprobe", 0o755)
    if remote_sha: FFMPEG_SHA_FILE.write_text(remote_sha)
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
            for part in getattr(item, "iterParts", lambda: [])():
                if os.path.abspath(part.file) == abs_path:
                    return item
    return None

# ==============================
# NFO handling
# ==============================
def compute_nfo_hash(nfo_path):
    h = hashlib.sha256()
    with open(nfo_path,"rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def apply_nfo(ep, file_path):
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size==0: return False
    nfo_hash = compute_nfo_hash(nfo_path)
    cached_hash = cache.get(file_path, {}).get("nfo_hash")
    if not config.get("always_apply_nfo", False) and cached_hash==nfo_hash:
        if detail: print(f"[DEBUG] NFO unchanged: {nfo_path}")
        return False
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        ep.editTitle(root.findtext("title",""), locked=True)
        ep.editSortTitle(root.findtext("aired",""), locked=True)
        ep.editSummary(root.findtext("plot",""), locked=True)
        update_cache(file_path, ep.key, nfo_hash)
        try: nfo_path.unlink()
        except: pass
        return True
    except Exception as e:
        logging.error(f"Error processing {nfo_path}: {e}")
        return False

# ==============================
# Subtitle extraction & upload
# ==============================
LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr","spa":"es",
            "ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}

def map_lang(code): return LANG_MAP.get(code.lower(),"und")

def extract_subtitles(video_path):
    base, _ = os.path.splitext(video_path)
    srt_files = []
    try:
        result = subprocess.run(
            [str(FFMPEG_BIN.parent/"ffprobe"), "-v","error","-select_streams","s",
             "-show_entries","stream=index:stream_tags=language,codec_name",
             "-of","json", video_path],
            capture_output=True, text=True, check=True
        )
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags",{}).get("language","und"))
            srt = f"{base}.{lang}{Path(video_path).suffix}"
            if os.path.exists(srt): continue
            subprocess.run([str(FFMPEG_BIN), "-y","-i",video_path,"-map",f"0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            srt_files.append((srt, lang))
    except Exception as e:
        logging.error(f"[ERROR] ffprobe/ffmpeg failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep, srt_files):
    for srt, lang in srt_files:
        try:
            with api_semaphore:
                ep.uploadSubtitles(srt, language=lang)
                time.sleep(request_delay)
        except Exception as e:
            logging.error(f"[ERROR] Subtitle upload failed: {srt} - {e}")

# ==============================
# File processing
# ==============================
def process_file(file_path, ignore_processed=False):
    abs_path = Path(file_path).resolve()
    str_path = str(abs_path)
    if not ignore_processed and str_path in processed_files: return False
    if abs_path.suffix.lower() not in VIDEO_EXTS: return False

    plex_item = None
    if str_path in cache and cache[str_path].get("plex_id"):
        try: plex_item = plex.fetchItem(cache[str_path]["plex_id"])
        except: plex_item = None

    if not plex_item: plex_item = find_plex_item(str_path)
    if plex_item: update_cache(str_path, plex_item.key, cache.get(str_path, {}).get("nfo_hash"))

    success = False
    nfo_path = abs_path.with_suffix(".nfo")
    if nfo_path.exists() and nfo_path.stat().st_size>0 and plex_item:
        success = apply_nfo(plex_item, str_path)
    processed_files.add(str_path)

    if subtitles_enabled and plex_item:
        srt_files = extract_subtitles(str_path)
        upload_subtitles(plex_item, srt_files)

    return success

# ==============================
# Watchdog handler
# ==============================
class WatchHandler(FileSystemEventHandler):
    def __init__(self):
        self.debounce = {}
        self.lock = threading.Lock()

    def on_any_event(self, event):
        if event.is_directory: return
        path = str(Path(event.src_path).resolve())
        with self.lock:
            pending_events[path] = time.time()

def watch_worker():
    while True:
        now = time.time()
        to_process = []
        with pending_lock:
            for path, ts in list(pending_events.items()):
                if now - ts >= watch_debounce_delay:
                    to_process.append(path)
                    del pending_events[path]
        for path in to_process:
            process_file(path)
        time.sleep(0.5)

# ==============================
# Scan libraries initially
# ==============================
def scan_and_update_cache():
    global cache
    all_files = []
    for lib_id in config["plex_library_ids"]:
        try: section = plex.library.sectionByID(lib_id)
        except: continue
        for p in getattr(section,"locations",[]):
            for root, dirs, files in os.walk(p):
                for f in files:
                    if f.lower().endswith(VIDEO_EXTS):
                        all_files.append(os.path.abspath(os.path.join(root,f)))

    for f in all_files:
        if f not in cache:
            plex_item = find_plex_item(f)
            if plex_item: update_cache(f, plex_item.key)
        nfo_path = Path(f).with_suffix(".nfo")
        if nfo_path.exists() and nfo_path.stat().st_size>0:
            plex_item = find_plex_item(f)
            if plex_item: apply_nfo(plex_item, f)
    save_cache()

# ==============================
# Main
# ==============================
def main():
    setup_ffmpeg()
    scan_and_update_cache()

    # Multithreaded processing
    if threads>1:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(process_file, f): f for f in cache.keys()}
            for fut in as_completed(futures): _ = fut.result()
    else:
        for f in cache.keys(): process_file(f)

    save_cache()

    # Watchdog monitoring
    if config.get("watch_folders", False) and not DISABLE_WATCHDOG:
        observer = Observer()
        handler = WatchHandler()
        for lib_id in config["plex_library_ids"]:
            try: section = plex.library.sectionByID(lib_id)
            except: continue
            for path in getattr(section,"locations",[]):
                observer.schedule(handler, path, recursive=True)
        observer.start()

        # Start worker thread for debounced processing
        threading.Thread(target=watch_worker, daemon=True).start()

        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__=="__main__":
    main()
