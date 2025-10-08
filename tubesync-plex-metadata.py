#!/usr/bin/env python3
import os
import sys
import json
import time
import threading
import queue
import hashlib
import logging
import platform
import shutil
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib3.util.retry import Retry
import requests
from requests.adapters import HTTPAdapter

# XML parsing
import lxml.etree as ET

# Plex
from plexapi.server import PlexServer

# File monitoring
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, PatternMatchingEventHandler

# argparse
import argparse

# ==============================
# Arguments
# ==============================
parser = argparse.ArgumentParser(description="TubeSync Plex Metadata")
parser.add_argument("--config", required=True, help="Path to config file")
parser.add_argument("--disable-watchdog", action="store_true", help="Disable folder watchdog")
parser.add_argument("--DETAIL", action="store_true", help="Enable detailed logging")
parser.add_argument("--debug-http", action="store_true", help="Enable HTTP debug logging")
parser.add_argument("--debug", action="store_true", help="Enable debug mode (implies DETAIL logging)")
parser.add_argument("--base-dir", help="Base directory override", default=os.environ.get("BASE_DIR", str(Path(__file__).parent.resolve())))
args = parser.parse_args()

# ==============================
# Globals
# ==============================
BASE_DIR = Path(args.base_dir).resolve()
DISABLE_WATCHDOG = args.disable_watchdog
DETAIL = args.DETAIL or args.debug
DEBUG_HTTP = args.debug_http

CONFIG_FILE = Path(args.config).resolve()
CACHE_FILE = CONFIG_FILE.parent / "tubesync_cache.json"

VENVDIR = BASE_DIR / "venv"
FFMPEG_BIN = VENVDIR / "bin/ffmpeg"
FFPROBE_BIN = VENVDIR / "bin/ffprobe"
FFMPEG_SHA_FILE = BASE_DIR / ".ffmpeg_md5"

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
cache_lock = threading.Lock()

# Language mapping for subtitles
LANG_MAP = {
    "eng": "en", "jpn": "ja", "kor": "ko", "fre": "fr", "fra": "fr",
    "spa": "es", "ger": "de", "deu": "de", "ita": "it", "chi": "zh", "und": "und"
}

def map_lang(code):
    return LANG_MAP.get(code.lower(), "und")

# ==============================
# Default config skeleton
# ==============================
default_config = {
    "_comment": {
        "PLEX_BASE_URL": "Base URL of your Plex server (e.g., http://localhost:32400).",
        "PLEX_TOKEN": "Your Plex authentication token.",
        "PLEX_LIBRARY_IDS": "List of Plex library IDs to sync (e.g., [10,21,35]).",
        "SILENT": "true = only summary logs, False = detailed logs",
        "DETAIL": "true = verbose mode (debug output)",
        "SUBTITLES": "true = extract and upload SUBTITLES",
        "THREADS": "Number of worker THREADS for initial scanning",
        "MAX_CONCURRENT_REQUESTS": "Max concurrent Plex API requests",
        "REQUEST_DELAY": "Delay between Plex API requests (sec)",
        "WATCH_FOLDERS": "true = enable real-time folder monitoring",
        "WATCH_DEBOUNCE_DELAY": "Debounce time (sec) before processing events",
        "ALWAYS_APPLY_NFO": "true = always apply NFO metadata regardless of hash",
        "DELETE_NFO_AFTER_APPLY": "true = remove NFO file after applying"
    },
    "PLEX_BASE_URL": "",
    "PLEX_TOKEN": "",
    "PLEX_LIBRARY_IDS": [],
    "SILENT": False,
    "DETAIL": False,
    "SUBTITLES": False,
    "THREADS": 8,
    "MAX_CONCURRENT_REQUESTS": 4,
    "REQUEST_DELAY": 0.2,
    "WATCH_FOLDERS": False,
    "WATCH_DEBOUNCE_DELAY": 3,
    "ALWAYS_APPLY_NFO": False,
    "DELETE_NFO_AFTER_APPLY": True,
}

# ==============================
# Load config (create if missing)
# ==============================
if not CONFIG_FILE.exists():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

with CONFIG_FILE.open("r", encoding="utf-8") as f:
    config = json.load(f)

# ==============================
# Apply config to globals
# ==============================
if DISABLE_WATCHDOG:
    config["WATCH_FOLDERS"] = False

# Config → global variables
DETAIL                 = DETAIL or config.get("DETAIL", False)
SILENT                 = config.get("SILENT", False)
DELETE_NFO_AFTER_APPLY = config.get("DELETE_NFO_AFTER_APPLY", True)
SUBTITLES_ENABLED      = config.get("SUBTITLES", False)
ALWAYS_APPLY_NFO       = config.get("ALWAYS_APPLY_NFO", True)
THREADS                = config.get("THREADS", 8)
MAX_CONCURRENT_REQUESTS= config.get("MAX_CONCURRENT_REQUESTS", 2)
REQUEST_DELAY          = config.get("REQUEST_DELAY", 0.1)
WATCH_FOLDERS          = config.get("WATCH_FOLDERS", True)
WATCH_DEBOUNCE_DELAY   = config.get("WATCH_DEBOUNCE_DELAY", 2)

api_semaphore = threading.Semaphore(MAX_CONCURRENT_REQUESTS)

# ==============================
# Logging setup
# ==============================

# Remove existing handlers
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Determine log level
if args.debug:
    log_level = logging.DEBUG        # --debug
elif SILENT:
    log_level = logging.WARNING      # summary mode
else:
    log_level = logging.INFO         # normal logs

logging.basicConfig(
    level=log_level,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True
)

# Separate HTTP debug log level
if not DEBUG_HTTP:
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

# ==============================
# Log helpers
# ==============================
def log_detail(msg):
    """ DETAIL only logs """
    if DETAIL and not SILENT:
        logging.info(f"[DETAIL] {msg}")

def log_debug(msg):
    """ DEBUG only logs """
    if args.debug:
        logging.debug(f"[DEBUG] {msg}")

# ==============================
# Initial logging of config
# ==============================
logging.info(f"BASE_DIR = {BASE_DIR}")
logging.info(f"CONFIG_FILE = {CONFIG_FILE}")
logging.info(f"VENVDIR = {VENVDIR}")
logging.info(f"FFMPEG_BIN = {FFMPEG_BIN}")
logging.info(f"FFPROBE_BIN = {FFPROBE_BIN}")
logging.info(f"DISABLE_WATCHDOG = {DISABLE_WATCHDOG}")
logging.info(f"DETAIL = {DETAIL}")
logging.info(f"DEBUG_HTTP = {DEBUG_HTTP}")
logging.info(f"SILENT = {SILENT}")
logging.info(f"DELETE_NFO_AFTER_APPLY = {DELETE_NFO_AFTER_APPLY}")
logging.info(f"SUBTITLES_ENABLED = {SUBTITLES_ENABLED}")
logging.info(f"ALWAYS_APPLY_NFO = {ALWAYS_APPLY_NFO}")
logging.info(f"THREADS = {THREADS}")
logging.info(f"MAX_CONCURRENT_REQUESTS = {MAX_CONCURRENT_REQUESTS}")
logging.info(f"REQUEST_DELAY = {REQUEST_DELAY}")
logging.info(f"WATCH_FOLDERS = {WATCH_FOLDERS}")
logging.info(f"WATCH_DEBOUNCE_DELAY = {WATCH_DEBOUNCE_DELAY}")

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
# Connect to Plex
# ==============================
try:
    plex = PlexServerWithHTTPDebug(
        config["PLEX_BASE_URL"],
        config["PLEX_TOKEN"],
        debug_http=DEBUG_HTTP
    )
except Exception as e:
    logging.error(f"Failed to connect to Plex: {e}")
    sys.exit(1)

# ==============================
# Cache handling (integrated by video)
# ==============================
if CACHE_FILE.exists():
    with CACHE_FILE.open("r", encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}

cache_modified = False
cache_lock = threading.Lock()  # 🔹 Added to ensure thread-safety

def save_cache():
    global cache_modified
    with cache_lock:
        if cache_modified:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            logging.info(f"[CACHE] Saved to {CACHE_FILE}, {len(cache)} entries")
            cache_modified = False

def update_cache(video_path, ratingKey=None, nfo_hash=None):
    """
    Add or update an entry in the cache.
    """
    global cache_modified
    path = str(video_path)
    with cache_lock:
        current = cache.get(path, {})
        if ratingKey is not None:
            current["ratingKey"] = ratingKey
        if nfo_hash is not None:
            current["nfo_hash"] = nfo_hash
        cache[path] = current
        cache_modified = True
        if DETAIL:
            logging.debug(f"[CACHE] update_cache: {path} => {current}")

def remove_from_cache(video_path):
    """
    Remove a file entry from the cache (safe even if it doesn't exist).
    """
    global cache_modified
    path = str(video_path)
    with cache_lock:
        if path in cache:
            cache.pop(path, None)
            cache_modified = True
            if DETAIL:
                logging.debug(f"[CACHE] remove_from_cache: {path}")

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
        logging.error(f"Unsupported arch: {arch}")
        return  # No longer force exit here

    md5_url = url + ".md5"
    tmp_dir = Path("/tmp/ffmpeg_dl")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tar_path = tmp_dir / "ffmpeg.tar.xz"

    try:
        r = requests.get(md5_url, timeout=10)
        r.raise_for_status()
        remote_md5 = r.text.strip().split()[0]
        logging.info(f"[DEBUG] Remote MD5: {remote_md5}")
    except Exception as e:
        logging.warning(f"Failed to fetch remote MD5: {e}")
        remote_md5 = None

    local_md5 = FFMPEG_SHA_FILE.read_text().strip() if FFMPEG_SHA_FILE.exists() else None
    if FFMPEG_BIN.exists() and FFPROBE_BIN.exists() and remote_md5 and local_md5 == remote_md5:
        logging.info("FFmpeg is up-to-date (MD5 match)")
        return

    if FFMPEG_BIN.exists(): FFMPEG_BIN.unlink(missing_ok=True)
    if FFPROBE_BIN.exists(): FFPROBE_BIN.unlink(missing_ok=True)

    logging.info("Downloading FFmpeg...")
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(tar_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        logging.error(f"Failed to download FFmpeg: {e}")
        return

    if remote_md5:
        h = hashlib.md5()
        with open(tar_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        if h.hexdigest() != remote_md5:
            logging.error("Downloaded FFmpeg MD5 mismatch, aborting")
            return

    try:
        extract_dir = tmp_dir / "extract"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True)
        subprocess.run(["tar", "-xJf", str(tar_path), "-C", str(extract_dir)], check=True)
        ffmpeg_path = next(extract_dir.glob("**/ffmpeg"))
        ffprobe_path = next(extract_dir.glob("**/ffprobe"))
        shutil.move(str(ffmpeg_path), FFMPEG_BIN)
        shutil.move(str(ffprobe_path), FFPROBE_BIN)
        os.chmod(FFMPEG_BIN, 0o755)
        os.chmod(FFPROBE_BIN, 0o755)
        if remote_md5: FFMPEG_SHA_FILE.write_text(remote_md5)
    except Exception as e:
        logging.error(f"FFmpeg extraction/move failed: {e}")
        return
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    env = os.environ.copy()
    env["PATH"] = f"{FFMPEG_BIN.parent}:{env.get('PATH','')}"
    if DETAIL: logging.info("FFmpeg installed/updated successfully")

# ==============================
# Plex helpers
# ==============================
def find_plex_item(abs_path):
    abs_path = os.path.abspath(abs_path)
    for lib_id in config.get("PLEX_LIBRARY_IDS", []):
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue

        # section.TYPE may not exist; use section.TYPE or section.type if present
        section_type = getattr(section, "TYPE", None) or getattr(section, "type", "")
        section_type = str(section_type).lower()
        if section_type == "show":
            results = section.search(libtype="episode")
        elif section_type in ("movie", "video"):
            results = section.search(libtype="movie")
        else:
            # try a broad search fallback
            results = section.search()

        for item in results:
            # parts: try several access patterns
            parts_iter = []
            try:
                parts_iter = item.iterParts()
            except Exception:
                try:
                    parts_iter = getattr(item, "parts", []) or []
                except Exception:
                    parts_iter = []

            for part in parts_iter:
                try:
                    if os.path.abspath(part.file) == abs_path:
                        return item
                except Exception:
                    continue
    return None

# ==============================
# NFO Processing (safe titleSort handling, retry-friendly)
# ==============================
deleted_nfo_set = set()
nfo_lock = threading.Lock()

def compute_nfo_hash(nfo_path):
    try:
        with open(nfo_path, "rb") as f:
            data = f.read()
        h = hashlib.md5(data).hexdigest()
        if DETAIL:
            logging.debug(f"[NFO] compute_nfo_hash: {nfo_path} -> {h}")
        return h
    except Exception as e:
        logging.error(f"[NFO] Failed to compute NFO hash: {nfo_path} - {e}")
        return None

def safe_edit(ep, title=None, summary=None, aired=None):
    try:
        kwargs = {}
        if title is not None:
            kwargs['title.value'] = title
            kwargs['title.locked'] = 1
        if summary is not None:
            kwargs['summary.value'] = summary
            kwargs['summary.locked'] = 1
        if aired is not None:
            kwargs['originallyAvailableAt.value'] = aired
            kwargs['originallyAvailableAt.locked'] = 1

        if kwargs:
            ep.edit(**kwargs)
            ep.reload()
        return True
    except Exception as e:
        logging.error(f"[SAFE_EDIT] Failed to edit item: {e}", exc_info=True)
        return False

def apply_nfo(ep, file_path):
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False

    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title", "").strip() or None
        plot = root.findtext("plot", "").strip() or None
        aired = root.findtext("aired", "").strip() or None
        title_sort = root.findtext("titleSort", "").strip() or title

        if DETAIL:
            logging.debug(f"[-] Applying NFO: {file_path} -> {title}")

        if not safe_edit(ep, title=title, summary=plot, aired=aired):
            return False

        if title_sort:
            try:
                ep.editSortTitle(title_sort, locked=True)
            except Exception:
                ep.edit(**{"titleSort.value": title_sort, "titleSort.locked": 1})
            ep.reload()

        return True
    except Exception as e:
        logging.error(f"[!] Error applying NFO {nfo_path}: {e}", exc_info=True)
        return False

def process_nfo(file_path):
    p = Path(file_path)
    if p.suffix.lower() == ".nfo":
        nfo_path = p
        video_path = p.with_suffix("")
        if not video_path.exists():
            for ext in VIDEO_EXTS:
                candidate = p.with_suffix(ext)
                if candidate.exists():
                    video_path = candidate
                    break
    else:
        video_path = p
        nfo_path = p.with_suffix(".nfo")

    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False

    str_video_path = str(video_path.resolve())
    nfo_hash = compute_nfo_hash(nfo_path)
    if nfo_hash is None:
        return False

    cached = cache.get(str_video_path, {})
    cached_hash = cached.get("nfo_hash")

    # ✅ If NFO has already been applied, skip Plex calls
    if cached_hash == nfo_hash and not ALWAYS_APPLY_NFO:
        logging.info(f"[CACHE] Skipping already applied NFO: {str_video_path}")
        if DELETE_NFO_AFTER_APPLY:
            with nfo_lock:
                if nfo_path not in deleted_nfo_set:
                    try:
                        nfo_path.unlink()
                        if DETAIL:
                            logging.debug(f"[NFO] Deleted already applied NFO: {nfo_path}")
                    except Exception as e:
                        logging.warning(f"[WARN] Failed to delete NFO {nfo_path}: {e}")
                    deleted_nfo_set.add(nfo_path)
        return True  # Considered successful even when skipped

    # ✅ Cache mismatch or forced application — call Plex
    plex_item = None
    ratingKey = cached.get("ratingKey")
    if cached_hash != nfo_hash or ALWAYS_APPLY_NFO:
        if ratingKey:
            try:
                plex_item = plex.fetchItem(ratingKey)
            except Exception:
                plex_item = None

        if not plex_item:
            plex_item = find_plex_item(str_video_path)
            if plex_item:
                update_cache(str_video_path, ratingKey=plex_item.ratingKey)
            else:
                logging.warning(f"[WARN] Plex item not found for {str_video_path}")
                return False  # 🔹 Fail and allow watchdog to retry

    # ✅ Apply NFO
    if plex_item:
        success = apply_nfo(plex_item, str_video_path)
        if success:
            update_cache(str_video_path, ratingKey=plex_item.ratingKey, nfo_hash=nfo_hash)
            if DELETE_NFO_AFTER_APPLY:
                with nfo_lock:
                    if nfo_path not in deleted_nfo_set:
                        try:
                            nfo_path.unlink()
                        except Exception as e:
                            logging.warning(f"[WARN] Failed to delete NFO {nfo_path}: {e}")
                        deleted_nfo_set.add(nfo_path)
            return True
        else:
            return False  # 🔹 Return False if failed

    return True  # No Plex call needed

# ==============================
# Unified file processing (video + NFO) — thread-safe with nfo_hash validation
# ==============================
processed_files = set()
processed_files_lock = threading.Lock()
file_queue = queue.Queue()
logged_failures = set()
logged_successes = set()

def process_file(file_path, schedule_timer=False):
    """
    Process file_path
    schedule_timer: if True, schedules a delayed ratingKey repair for new files
    """
    abs_path = Path(file_path).resolve()
    str_path = str(abs_path)

    # Thread-safe duplicate prevention
    with processed_files_lock:
        if str_path in processed_files:
            return False
        processed_files.add(str_path)

    try:
        # ===== NFO Processing =====
        nfo_applied = True
        nfo_hash = None
        if abs_path.suffix.lower() == ".nfo":
            nfo_applied = process_nfo(str_path)
        elif abs_path.suffix.lower() in VIDEO_EXTS:
            nfo_path = abs_path.with_suffix(".nfo")
            if nfo_path.exists():
                nfo_applied = process_nfo(str(nfo_path))

        # ===== Cache Check =====
        cached_entry = cache.get(str_path)
        ratingKey = cached_entry.get("ratingKey") if cached_entry else None
        nfo_hash = cached_entry.get("nfo_hash") if cached_entry else None

        # ===== Determine Status =====
        if nfo_applied and ratingKey and nfo_hash:
            if str_path not in logged_successes:
                logging.info(f"[INFO] Skipping Plex call (NFO applied & cached): {str_path}")
                logged_successes.add(str_path)
            logged_failures.discard(str_path)
            return True
        elif ratingKey and not nfo_hash:
            if str_path not in logged_successes:
                logging.info(f"[INFO] Pending NFO apply (ratingKey exists, missing NFO hash): {str_path}")
                logged_successes.add(str_path)
            logged_failures.discard(str_path)
            return True
        else:
            plex_item = find_plex_item(str_path)
            if plex_item:
                ratingKey = plex_item.ratingKey
                update_cache(str_path, ratingKey=ratingKey)
                logging.info(f"[INFO] Plex item found and cached: {str_path} (ratingKey={ratingKey})")
            else:
                update_cache(str_path, ratingKey=None)
                logging.info(f"[INFO] File added to cache (no ratingKey found): {str_path}")

                # 🔹 Schedule timer for watchdog event
                if schedule_timer:
                    logging.info(f"[CACHE] 🔹 RatingKey missing for {str_path}, scheduling repair in {DELAY_AFTER_NEW_FILE}s")
                    schedule_cache_repair(DELAY_AFTER_NEW_FILE)

            logged_failures.discard(str_path)
            logged_successes.add(str_path)
            return True

    except Exception as e:
        if str_path not in logged_failures:
            logging.warning(f"[WARN] Error while processing {str_path}: {e}")
            logged_failures.add(str_path)
        return False

# ==============================
# Subtitle extraction & upload
# ==============================
def extract_subtitles(video_path):
    base, _ = os.path.splitext(video_path)
    srt_files=[]
    try:
        result=subprocess.run([str(FFPROBE_BIN),"-v","error","-select_streams","s",
                               "-show_entries","stream=index:stream_tags=language,codec_name",
                               "-of","json",video_path],
                              capture_output=True,text=True,check=True)
        streams=json.loads(result.stdout).get("streams",[])
        for s in streams:
            idx=s.get("index")
            codec=s.get("codec_name","")
            if codec.lower() in ["pgs","dvdsub","hdmv_pgs","vobsub"]:
                logging.warning(f"Skipping unsupported subtitle codec {codec} in {video_path}")
                continue
            lang=map_lang(s.get("tags",{}).get("language","und"))
            srt=f"{base}.{lang}.srt"
            if os.path.exists(srt): continue
            subprocess.run([str(FFMPEG_BIN),"-y","-i",video_path,"-map",f"0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
            srt_files.append((srt,lang))
    except Exception as e:
        logging.error(f"[ERROR] Subtitle extraction failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep,srt_files):
    for srt,lang in srt_files:
        retries=3
        while retries>0:
            try:
                with api_semaphore:
                    # plexapi may provide different method names; try common ones
                    if hasattr(ep, "uploadSubtitles"):
                        ep.uploadSubtitles(srt,language=lang)
                    elif hasattr(ep, "addSubtitles"):
                        ep.addSubtitles(srt, language=lang)
                    else:
                        # fallback: try library-level upload (not ideal)
                        try:
                            ep.uploadSubtitles(srt, language=lang)
                        except Exception:
                            raise
                    time.sleep(REQUEST_DELAY)
                break
            except Exception as e:
                retries-=1
                logging.error(f"[ERROR] Subtitle upload failed: {srt} - {e}, retries left: {retries}")

# ==============================
# Global Timers / Locks
# ==============================
CACHE_REPAIR_INTERVAL = 300        # Default interval (5 minutes)
DELAY_AFTER_NEW_FILE = 60          # 1 minute after new file detection
repair_timer = None
repair_lock = threading.Lock()


def schedule_cache_repair(delay):
    """Schedule cache repair after the specified delay; cancel existing timer if present."""
    global repair_timer
    with repair_lock:
        if repair_timer:
            logging.debug(f"[CACHE] Existing repair timer canceled")
            repair_timer.cancel()
        repair_timer = threading.Timer(delay, repair_wrapper)
        repair_timer.daemon = True
        repair_timer.start()
        logging.debug(f"[CACHE] Repair timer scheduled to run in {delay} seconds ({time.strftime('%H:%M:%S')})")


def repair_wrapper():
    """Execute the actual repair, then reschedule with the default interval."""
    global repair_timer
    logging.debug(f"[CACHE] Repair wrapper triggered at {time.strftime('%H:%M:%S')}")
    try:
        repair_missing_ratingkeys()
    except Exception as e:
        logging.error(f"[CACHE] repair_missing_ratingkeys failed: {e}", exc_info=True)

    # Reschedule for the default interval
    logging.debug(f"[CACHE] Rescheduling next repair in {CACHE_REPAIR_INTERVAL} seconds")
    schedule_cache_repair(CACHE_REPAIR_INTERVAL)

# ==============================
# Watchdog Handler (integrated VIDEO_EXTS + NFO handling, intelligent retry)
# ==============================
class MediaFileHandler(FileSystemEventHandler):
    MAX_NFO_RETRY = 5  # NFO retry limit
    MAX_RETRY_DELAY = 600  # 10 minutes

    def __init__(self, nfo_wait=30, video_wait=5, debounce_delay=1.0):
        self.nfo_wait = nfo_wait
        self.video_wait = video_wait
        self.debounce_delay = debounce_delay
        # retry_queue = { path: (next_time, delay, retry_count, is_nfo) }
        self.retry_queue = {}
        self.last_event_time = {}

    # ==============================
    # Utility
    # ==============================
    def _debounce(self, path):
        now = time.time()
        last_time = self.last_event_time.get(path, 0)
        if now - last_time < self.debounce_delay:
            return False
        self.last_event_time[path] = now
        return True

    def _enqueue_retry(self, path, delay, retry_count=0, is_nfo=False):
        """Add to retry queue"""
        self.retry_queue[path] = (time.time() + delay, delay, retry_count, is_nfo)
        logging.debug(f"[WATCHDOG] Enqueued for retry ({'NFO' if is_nfo else 'VIDEO'}): {path} (delay={delay}s, retry={retry_count})")

    # ==============================
    # Retry queue processing
    # ==============================
    def process_retry_queue(self):
        global cache_modified
        now = time.time()
        ready = [p for p, (t, _, _, _) in self.retry_queue.items() if t <= now]

        for path in ready:
            next_time, delay, retry_count, is_nfo = self.retry_queue.pop(path)
            p = Path(path)

            if not p.exists():
                logging.info(f"[WATCHDOG] Path no longer exists, removing from cache: {path}")
                with cache_lock:
                    if path in cache:
                        cache.pop(path)
                        cache_modified = True
                continue

            ext = p.suffix.lower()

            # Folder handling
            if p.is_dir():
                for f in p.rglob("*"):
                    if not f.is_file():
                        continue
                    fext = f.suffix.lower()
                    if fext in VIDEO_EXTS:
                        self._enqueue_retry(str(f.resolve()), self.video_wait)
                    elif fext == ".nfo":
                        self._enqueue_retry(str(f.resolve()), self.nfo_wait, is_nfo=True)
                continue

            # Single file handling
            success = False
            if ext in VIDEO_EXTS:
                logging.info(f"[WATCHDOG] Processing video: {path}")
                success = process_file(str(p.resolve()))
            elif ext == ".nfo":
                logging.info(f"[WATCHDOG] Processing NFO: {path}")
                success = process_nfo(str(p.resolve()))
            else:
                logging.debug(f"[WATCHDOG] Ignored non-video/non-NFO file: {p}")
                continue

            # Retry on failure
            if not success:
                if is_nfo and retry_count + 1 >= self.MAX_NFO_RETRY:
                    logging.warning(f"[WATCHDOG] Max retries reached for NFO: {path}")
                    continue
                new_delay = min(delay * 2, self.MAX_RETRY_DELAY)
                self._enqueue_retry(path, new_delay, retry_count + 1, is_nfo)
                logging.warning(f"[WATCHDOG] Retry scheduled for {path} in {new_delay}s (retry #{retry_count + 1})")

        if cache_modified:
            logging.info(f"[CACHE] Saving cache, {len(cache)} entries")
            save_cache()
            cache_modified = False

    # ==============================
    # Event Handlers
    # ==============================
    def on_created(self, event):
        if not self._debounce(event.src_path):
            return
        path = str(Path(event.src_path).resolve())
        ext = Path(path).suffix.lower()

        # 🎬 Video files and 📄 NFO files only
        if ext in VIDEO_EXTS:
            self._enqueue_retry(path, self.video_wait, is_nfo=False)
        elif ext == ".nfo":
            self._enqueue_retry(path, self.nfo_wait, is_nfo=True)
        else:
            logging.debug(f"[WATCHDOG] Ignored file: {path}")

    def on_deleted(self, event):
        self._handle_deleted(str(Path(event.src_path).resolve()))

    def on_moved(self, event):
        src = str(Path(event.src_path).resolve())
        dest = str(Path(event.dest_path).resolve()) if getattr(event, "dest_path", None) else None
        self._handle_deleted(src)
        if dest and not event.is_directory:
            self._handle_created(dest)

    # ==============================
    # Cache removal (on delete or folder move)
    # ==============================
    def _handle_deleted(self, abs_path):
        abs_path = str(Path(abs_path).resolve())
        if not self._debounce(abs_path):
            return
        keys_to_remove = [k for k in cache.keys() if k == abs_path or k.startswith(f"{abs_path}/")]
        if not keys_to_remove:
            return  # 🔹 No changes — return immediately
        for k in keys_to_remove:
            remove_from_cache(k)
            logging.info(f"[CACHE] Removed {k} (deleted/moved)")
        global cache_modified
        cache_modified = True

    # ==============================
    # Handle create/move events
    # ==============================
    def _handle_created(self, abs_path):
        """Register only video/NFO files including inside folders"""
        abs_path = str(Path(abs_path).resolve())
        if not self._debounce(abs_path):
            return

        p = Path(abs_path)
        paths = []
        if p.is_dir():
            paths = [str(f.resolve()) for f in p.rglob("*") if f.is_file()]
        else:
            paths = [abs_path]

        for f in paths:
            ext = Path(f).suffix.lower()
            if ext in VIDEO_EXTS:
                self._enqueue_retry(f, self.video_wait, is_nfo=False)
            elif ext == ".nfo":
                self._enqueue_retry(f, self.nfo_wait, is_nfo=True)
            else:
                logging.debug(f"[WATCHDOG] Ignored file in folder: {f}")

# ==============================
# Watchdog Observer Loop
# ==============================
def start_watchdog(base_dirs):
    observer = Observer()
    handler = MediaFileHandler(debounce_delay=WATCH_DEBOUNCE_DELAY)

    for d in base_dirs:
        observer.schedule(handler, d, recursive=True)
    observer.start()
    logging.info("[WATCHDOG] Started observer")

    # Schedule the first repair
    schedule_cache_repair(CACHE_REPAIR_INTERVAL)
    logging.info("[CACHE] Cache repair scheduler started")

    try:
        while True:
            try:
                handler.process_retry_queue()
            except Exception as e:
                logging.error(f"[WATCHDOG] process_retry_queue failed: {e}", exc_info=True)
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("[WATCHDOG] Stopping observer")
        observer.stop()
        with repair_lock:
            if repair_timer:
                repair_timer.cancel()
        observer.join()

# ==============================
# Cache Repair: Missing ratingKeys only
# ==============================
def repair_missing_ratingkeys():
    """Scan cache and restore missing ratingKeys from Plex."""
    missing = [
        path for path, data in cache.items()
        if data is not None and not data.get("ratingKey") and Path(path).exists()
    ]

    if not missing:
        logging.debug("[CACHE] No missing ratingKeys found.")
        return

    logging.info(f"[CACHE] Found {len(missing)} entries missing ratingKeys — attempting repair...")

    repaired = 0
    for path in missing:
        try:
            plex_item = find_plex_item(path)
            if plex_item:
                update_cache(path, ratingKey=plex_item.ratingKey)
                logging.info(f"[CACHE] Restored ratingKey for {path} → {plex_item.ratingKey}")
                repaired += 1
        except Exception as e:
            logging.warning(f"[CACHE] Failed to repair {path}: {e}")

    if repaired > 0:
        save_cache()
        logging.info(f"[CACHE] RatingKey repair completed — {repaired} entries updated.")
    else:
        logging.info("[CACHE] No ratingKeys could be repaired.")

# ==============================
# Scan: NFO only (new)
# ==============================
def scan_nfo_files(base_dirs):
    """
    base_dirs: can be a single Path or list[Path]
    """
    if isinstance(base_dirs, (str, Path)):
        base_dirs = [base_dirs]

    nfo_files = []
    for base_dir in base_dirs:
        for root, _, files in os.walk(base_dir):
            for f in files:
                if f.lower().endswith(".nfo"):
                    nfo_files.append(os.path.abspath(os.path.join(root, f)))

    if DETAIL:
        logging.debug(f"[SCAN] Found {len(nfo_files)} NFO files")
    return nfo_files

# ==============================
# Scan and update cache (thread-safe, integrated)
# ==============================
def scan_and_update_cache(base_dirs):
    """
    Cache update:
    1) Scan directories → current_files
    2) Compare with cache:
       - Files not in cache → add (fetch from Plex)
       - Files in cache but missing from disk → remove
    3) Save cache if any changes occurred
    """
    global cache, cache_modified

    if isinstance(base_dirs, (str, Path)):
        base_dirs = [base_dirs]

    current_files = set()
    for base_dir in base_dirs:
        for root, _, files in os.walk(base_dir):
            for f in files:
                abs_path = os.path.abspath(os.path.join(root, f))
                if abs_path.lower().endswith(VIDEO_EXTS):
                    current_files.add(abs_path)

    logging.info(f"[CACHE] Scanned {len(current_files)} video files in directories.")

    added_count = 0
    removed_count = 0

    with cache_lock:
        # ---- Add new files ----
        for path in current_files:
            if path not in cache:
                plex_item = find_plex_item(path)
                if plex_item:
                    cache[path] = {"ratingKey": plex_item.ratingKey}
                    logging.info(f"[CACHE] Added: {path} (ratingKey={plex_item.ratingKey})")
                else:
                    cache[path] = {}  # placeholder
                    logging.info(f"[CACHE] Added (no Plex match): {path}")
                added_count += 1
                cache_modified = True

        # ---- Remove missing files ----
        for path in list(cache.keys()):
            if path not in current_files:
                cache.pop(path, None)
                logging.info(f"[CACHE] Removed: {path} (file missing)")
                removed_count += 1
                cache_modified = True

    if cache_modified:
        save_cache()
        logging.info(f"[CACHE] Update complete: +{added_count}, -{removed_count}, total={len(cache)}")
    else:
        logging.info("[CACHE] No changes detected.")

def run_processing(base_dirs):
    """
    1) Update cache
    2) Process video + NFO files (ThreadPoolExecutor)
    3) Save final cache
    """
    # 1) Cache scan/update
    scan_and_update_cache(base_dirs)

    # 2) Video / NFO lists
    video_files = [f for f in cache.keys() if Path(f).suffix.lower() in VIDEO_EXTS]
    nfo_files = scan_nfo_files(base_dirs)

    logging.info(f"[MAIN] {len(video_files)} video files to process.")
    logging.info(f"[MAIN] {len(nfo_files)} NFO files to process.")

    # 3) Process with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        # NFO processing
        for nfo in nfo_files:
            executor.submit(process_nfo, nfo)
        # Video processing
        futures = {executor.submit(process_file, f): f for f in video_files}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logging.error(f"[MAIN] Failed: {futures[fut]} - {e}")

    # 4) Final cache save
    logging.debug("[CACHE] Final save_cache() called")
    save_cache()
    logging.info(f"[CACHE] Final cache saved successfully, {len(cache)} entries")
        
# ==============================
# Main NFO Processing Loop
# ==============================
def process_all_nfo(base_dirs):
    """
    base_dirs: can be a single Path or list[Path]
    Process all NFO files within base_dirs
    """
    if isinstance(base_dirs, (str, Path)):
        base_dirs = [base_dirs]

    nfo_files = []
    for base_dir in base_dirs:
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                if f.lower().endswith(".nfo"):
                    nfo_files.append(os.path.abspath(os.path.join(root, f)))

    if DETAIL:
        logging.debug(f"[SCAN] Found {len(nfo_files)} NFO files")

    for nfo_file in nfo_files:
        try:
            process_nfo(nfo_file)
        except Exception as e:
            logging.error(f"[NFO] Error processing {nfo_file}: {e}", exc_info=True)

# ==============================
# Main Execution
# ==============================
def main():
    setup_ffmpeg()

    base_dirs = []
    for lib_id in config.get("PLEX_LIBRARY_IDS", []):
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue
        base_dirs.extend(getattr(section, "locations", []))

    if DISABLE_WATCHDOG:
        logging.info("[MAIN] Running initial full processing (watchdog disabled)")
        run_processing(base_dirs)
    elif config.get("WATCH_FOLDERS", False):
        logging.info("[MAIN] Starting Watchdog mode")
        start_watchdog(base_dirs)

    logging.info("END")


if __name__ == "__main__":
    main()
