#!/usr/bin/env python3
import os, sys, json, time, threading, subprocess, shutil, hashlib, queue
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from plexapi.server import PlexServer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import platform, requests, logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import lxml.etree as ET
import argparse

# ==============================
# Arguments
# ==============================
PARSER = argparse.ArgumentParser(DESCRIPTION="TubeSync Plex Metadata")
parser.add_argument("--config", REQUIRED=True, HELP="Path to config file")
parser.add_argument("--disable-watchdog", ACTION="store_true", HELP="Disable folder watchdog")
parser.add_argument("--detail", ACTION="store_true", HELP="Enable detailed logging")
parser.add_argument("--debug-http", ACTION="store_true", HELP="Enable HTTP debug logging")
parser.add_argument("--debug", ACTION="store_true", HELP="Enable debug mode (implies detail logging)")
parser.add_argument("--base-dir", HELP="Base directory override", DEFAULT=os.environ.get("BASE_DIR", str(Path(__file__).parent.resolve())))
ARGS = parser.parse_args()

# ==============================
# Globals
# ==============================
BASE_DIR = Path(args.base_dir).resolve()
DISABLE_WATCHDOG = args.disable_watchdog
DETAIL = args.detail or args.debug
DEBUG_HTTP = args.debug_http

CONFIG_FILE = Path(args.config).resolve()
CACHE_FILE = CONFIG_FILE.parent / "tubesync_cache.json"

VENVDIR = BASE_DIR / "venv"
FFMPEG_BIN = VENVDIR / "bin/ffmpeg"
FFPROBE_BIN = VENVDIR / "bin/ffprobe"
FFMPEG_SHA_FILE = BASE_DIR / ".ffmpeg_md5"

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
CACHE_LOCK = threading.Lock()

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
DEFAULT_CONFIG = {
    "_comment": {
        "plex_base_url": "Base URL of your Plex server (e.g., http://localhost:32400).",
        "plex_token": "Your Plex authentication token.",
        "plex_library_ids": "List of Plex library IDs to sync (e.g., [10,21,35]).",
        "silent": "TRUE = only summary logs, False = detailed logs",
        "detail": "TRUE = verbose mode (debug output)",
        "subtitles": "TRUE = extract and upload subtitles",
        "always_apply_nfo": "TRUE = always apply NFO metadata regardless of hash",
        "threads": "Number of worker threads for initial scanning",
        "max_concurrent_requests": "Max concurrent Plex API requests",
        "request_delay": "Delay between Plex API requests (sec)",
        "watch_folders": "TRUE = enable real-time folder monitoring",
        "watch_debounce_delay": "Debounce time (sec) before processing events",
        "delete_nfo_after_apply": "TRUE = remove NFO file after applying"
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
    "watch_debounce_delay": 3,
    "delete_nfo_after_apply": True,
}

# ==============================
# Load config (create if missing)
# ==============================
if not CONFIG_FILE.exists():
    CONFIG_FILE.parent.mkdir(PARENTS=True, EXIST_OK=True)
    with CONFIG_FILE.open("w", ENCODING="utf-8") as f:
        json.dump(default_config, f, INDENT=4, ENSURE_ASCII=False)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

with CONFIG_FILE.open("r", ENCODING="utf-8") as f:
    CONFIG = json.load(f)

# ==============================
# Apply config to globals
# ==============================
if DISABLE_WATCHDOG:
    config["watch_folders"] = False

# Config → 전역 변수
DETAIL                 = DETAIL or config.get("detail", False)
SILENT                 = config.get("silent", False)
DELETE_NFO_AFTER_APPLY = config.get("delete_nfo_after_apply", True)
SUBTITLES_ENABLED      = config.get("subtitles", False)
ALWAYS_APPLY_NFO       = config.get("always_apply_nfo", True)
THREADS                = config.get("threads", 8)
MAX_CONCURRENT_REQUESTS= config.get("max_concurrent_requests", 2)
REQUEST_DELAY          = config.get("request_delay", 0.1)
WATCH_FOLDERS          = config.get("watch_folders", True)
WATCH_DEBOUNCE_DELAY   = config.get("watch_debounce_delay", 2)

API_SEMAPHORE = threading.Semaphore(MAX_CONCURRENT_REQUESTS)

# ==============================
# Initial logging of config
# ==============================
logging.info(f"SILENT = {SILENT}")
logging.info(f"DETAIL = {DETAIL}")
logging.info(f"DELETE_NFO_AFTER_APPLY = {DELETE_NFO_AFTER_APPLY}")
logging.info(f"SUBTITLES_ENABLED = {SUBTITLES_ENABLED}")
logging.info(f"ALWAYS_APPLY_NFO = {ALWAYS_APPLY_NFO}")
logging.info(f"THREADS = {THREADS}")
logging.info(f"MAX_CONCURRENT_REQUESTS = {MAX_CONCURRENT_REQUESTS}")
logging.info(f"REQUEST_DELAY = {REQUEST_DELAY}")
logging.info(f"WATCH_FOLDERS = {WATCH_FOLDERS}")
logging.info(f"WATCH_DEBOUNCE_DELAY = {WATCH_DEBOUNCE_DELAY}")

# ==============================
# Logging setup
# ==============================
if not DEBUG_HTTP:
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
LOG_LEVEL = logging.DEBUG if DETAIL else logging.INFO
logging.basicConfig(LEVEL=log_level, FORMAT='[%(levelname)s] %(message)s')

logging.info(f"BASE_DIR = {BASE_DIR}")
logging.info(f"CONFIG_FILE = {CONFIG_FILE}")
logging.info(f"VENVDIR = {VENVDIR}")
logging.info(f"FFMPEG_BIN = {FFMPEG_BIN}")
logging.info(f"FFPROBE_BIN = {FFPROBE_BIN}")
logging.info(f"DISABLE_WATCHDOG = {DISABLE_WATCHDOG}")
logging.info(f"DETAIL = {DETAIL}")
logging.info(f"DEBUG_HTTP = {DEBUG_HTTP}")

# ==============================
# HTTP debug session
# ==============================
class HTTPDebugSession(requests.Session):
    def __init__(self, ENABLE_DEBUG=False):
        super().__init__()
        self.ENABLE_DEBUG = enable_debug
        RETRIES = Retry(TOTAL=3, BACKOFF_FACTOR=0.3, STATUS_FORCELIST=[500,502,503,504])
        self.mount("http://", HTTPAdapter(MAX_RETRIES=retries))
        self.mount("https://", HTTPAdapter(MAX_RETRIES=retries))

    def send(self, request, **kwargs):
        if self.enable_debug:
            print("[HTTP DEBUG] REQUEST:", request.method, request.url)
        RESPONSE = super().send(request, **kwargs)
        if self.enable_debug:
            print("[HTTP DEBUG] RESPONSE:", response.status_code, response.reason)
        return response

# ==============================
# Plex server wrapper
# ==============================
class PlexServerWithHTTPDebug(PlexServer):
    def __init__(self, baseurl, token, DEBUG_HTTP=False):
        super().__init__(baseurl, token)
        self._DEBUG_SESSION = HTTPDebugSession(ENABLE_DEBUG=debug_http)

    def _request(self, path, METHOD="GET", HEADERS=None, PARAMS=None, DATA=None, TIMEOUT=None):
        URL = self._buildURL(path)
        REQ_HEADERS = headers or {}
        if self._token:
            req_headers["X-Plex-Token"] = self._token
        RESP = self._debug_session.request(method, url, HEADERS=req_headers, PARAMS=params, DATA=data, TIMEOUT=timeout)
        resp.raise_for_status()
        return resp

# ==============================
# Connect Plex
# ==============================
try:
    PLEX = PlexServerWithHTTPDebug(
        config["plex_base_url"],
        config["plex_token"],
        DEBUG_HTTP=DEBUG_HTTP
    )
except Exception as e:
    logging.error(f"Failed to connect to Plex: {e}")
    sys.exit(1)

# ==============================
# Cache handling (영상 기준으로 통합)
# ==============================
if CACHE_FILE.exists():
    with CACHE_FILE.open("r", ENCODING="utf-8") as f:
        CACHE = json.load(f)
else:
    CACHE = {}

CACHE_MODIFIED = False

def save_cache():
    global cache_modified
    with cache_lock:
        if cache_modified:
            CACHE_FILE.parent.mkdir(PARENTS=True, EXIST_OK=True)
            with CACHE_FILE.open("w", ENCODING="utf-8") as f:
                json.dump(cache, f, INDENT=2, ENSURE_ASCII=False)
            logging.info(f"[CACHE] Saved to {CACHE_FILE}")
            CACHE_MODIFIED = False

def update_cache(video_path, ratingKey=None, NFO_HASH=None):
    global cache_modified
    PATH = str(video_path)
    with cache_lock:
        CURRENT = cache.get(path, {})
        if ratingKey: current["ratingKey"] = ratingKey
        if nfo_hash: current["nfo_hash"] = nfo_hash
        cache[path] = current
        CACHE_MODIFIED = True
        if DETAIL:
            logging.debug(f"[CACHE] update_cache: {path} => {current}")

# ==============================
# FFmpeg setup
# ==============================
def setup_ffmpeg():
    ARCH = platform.machine()
    if ARCH == "x86_64":
        URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif ARCH == "aarch64":
        URL = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else:
        logging.error(f"Unsupported arch: {arch}")
        return  # 더 이상 강제 종료하지 않음

    MD5_URL = url + ".md5"
    TMP_DIR = Path("/tmp/ffmpeg_dl")
    tmp_dir.mkdir(PARENTS=True, EXIST_OK=True)
    TAR_PATH = tmp_dir / "ffmpeg.tar.xz"

    try:
        R = requests.get(md5_url, TIMEOUT=10)
        r.raise_for_status()
        REMOTE_MD5 = r.text.strip().split()[0]
        logging.info(f"[DEBUG] Remote MD5: {remote_md5}")
    except Exception as e:
        logging.warning(f"Failed to fetch remote MD5: {e}")
        REMOTE_MD5 = None

    LOCAL_MD5 = FFMPEG_SHA_FILE.read_text().strip() if FFMPEG_SHA_FILE.exists() else None
    if FFMPEG_BIN.exists() and FFPROBE_BIN.exists() and remote_md5 and LOCAL_MD5 == remote_md5:
        logging.info("FFmpeg up-to-date (MD5 match)")
        return

    if FFMPEG_BIN.exists(): FFMPEG_BIN.unlink(MISSING_OK=True)
    if FFPROBE_BIN.exists(): FFPROBE_BIN.unlink(MISSING_OK=True)

    logging.info("Downloading FFmpeg...")
    try:
        R = requests.get(url, STREAM=True, TIMEOUT=60)
        r.raise_for_status()
        with open(tar_path, "wb") as f:
            for chunk in r.iter_content(CHUNK_SIZE=8192):
                f.write(chunk)
    except Exception as e:
        logging.error(f"Failed to download FFmpeg: {e}")
        return

    if remote_md5:
        H = hashlib.md5()
        with open(tar_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        if h.hexdigest() != remote_md5:
            logging.error("Downloaded FFmpeg MD5 mismatch, aborting")
            return

    try:
        EXTRACT_DIR = tmp_dir / "extract"
        shutil.rmtree(extract_dir, IGNORE_ERRORS=True)
        extract_dir.mkdir(PARENTS=True)
        subprocess.run(["tar", "-xJf", str(tar_path), "-C", str(extract_dir)], CHECK=True)
        FFMPEG_PATH = next(extract_dir.glob("**/ffmpeg"))
        FFPROBE_PATH = next(extract_dir.glob("**/ffprobe"))
        shutil.move(str(ffmpeg_path), FFMPEG_BIN)
        shutil.move(str(ffprobe_path), FFPROBE_BIN)
        os.chmod(FFMPEG_BIN, 0o755)
        os.chmod(FFPROBE_BIN, 0o755)
        if remote_md5: FFMPEG_SHA_FILE.write_text(remote_md5)
    except Exception as e:
        logging.error(f"FFmpeg extraction/move failed: {e}")
        return
    finally:
        shutil.rmtree(tmp_dir, IGNORE_ERRORS=True)

    ENV = os.environ.copy()
    env["PATH"] = f"{FFMPEG_BIN.parent}:{env.get('PATH','')}"
    if DETAIL: logging.info("FFmpeg installed/updated successfully")

# ==============================
# Plex helpers
# ==============================
def find_plex_item(abs_path):
    ABS_PATH = os.path.abspath(abs_path)
    for lib_id in config.get("plex_library_ids", []):
        try:
            SECTION = plex.library.sectionByID(lib_id)
        except Exception:
            continue

        # section.TYPE may not exist; use section.TYPE or section.type if present
        SECTION_TYPE = getattr(section, "TYPE", None) or getattr(section, "type", "")
        SECTION_TYPE = str(section_type).lower()
        if SECTION_TYPE == "show":
            RESULTS = section.search(LIBTYPE="episode")
        elif section_type in ("movie", "video"):
            RESULTS = section.search(LIBTYPE="movie")
        else:
            # try a broad search fallback
            RESULTS = section.search()

        for item in results:
            # parts: try several access patterns
            PARTS_ITER = []
            try:
                PARTS_ITER = item.iterParts()
            except Exception:
                try:
                    PARTS_ITER = getattr(item, "parts", []) or []
                except Exception:
                    PARTS_ITER = []

            for part in parts_iter:
                try:
                    if os.path.abspath(part.file) == abs_path:
                        return item
                except Exception:
                    continue
    return None

# ==============================
# NFO Process (titleSort 안전 적용)
# ==============================
def compute_nfo_hash(nfo_path):
    try:
        with open(nfo_path, "rb") as f:
            DATA = f.read()
        H = hashlib.md5(data).hexdigest()
        if DETAIL:
            logging.debug(f"[NFO] compute_nfo_hash: {nfo_path} -> {h}")
        return h
    except Exception as e:
        logging.error(f"[NFO] compute_nfo_hash failed: {nfo_path} - {e}")
        return None

def safe_edit(ep, TITLE=None, SUMMARY=None, AIRED=None):
    """
    일반 필드(title, summary, aired) 편집
    """
    try:
        KWARGS = {}
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
        logging.error(f"[SAFE_EDIT] Failed to edit item: {e}", EXC_INFO=True)
        return False

def apply_nfo(ep, file_path):
    """
    NFO를 Plex 아이템에 적용
    - titleSort가 없으면 title로 대체
    - editSortTitle 사용으로 첫 글자 손실 방지
    """
    NFO_PATH = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().ST_SIZE == 0:
        return False

    try:
        TREE = ET.parse(str(nfo_path), PARSER=ET.XMLParser(RECOVER=True))
        ROOT = tree.getroot()
        TITLE = root.findtext("title", "").strip() or None
        PLOT = root.findtext("plot", "").strip() or None
        AIRED = root.findtext("aired", "").strip() or None
        TITLE_SORT = root.findtext("titleSort", "").strip() or title  # NFO 없으면 title 사용

        if DETAIL:
            logging.debug(f"[-] Applying NFO: {file_path} -> {title}")

        # 일반 필드 적용
        safe_edit(ep, TITLE=title, SUMMARY=plot, AIRED=aired)

        # titleSort는 editSortTitle로 적용
        if title_sort:
            try:
                ep.editSortTitle(title_sort, LOCKED=True)  # 첫 글자 손실 없음
            except Exception:
                # fallback: metadata.edit 사용
                ep.edit(**{"titleSort.value": title_sort, "titleSort.locked": 1})
            ep.reload()

        return True

    except Exception as e:
        logging.error(f"[!] Error applying NFO {nfo_path}: {e}", EXC_INFO=True)
        return False

def process_nfo(file_path):
    """
    단일 NFO 처리
    """
    P = Path(file_path)
    if p.suffix.lower() == ".nfo":
        NFO_PATH = p
        VIDEO_PATH = p.with_suffix("")  # video path 추정
        if not video_path.exists():
            for ext in VIDEO_EXTS:
                CANDIDATE = p.with_suffix(ext)
                if candidate.exists():
                    VIDEO_PATH = candidate
                    break
    else:
        VIDEO_PATH = p
        NFO_PATH = p.with_suffix(".nfo")

    if not nfo_path.exists() or nfo_path.stat().ST_SIZE == 0:
        return False

    STR_VIDEO_PATH = str(video_path.resolve())
    NFO_HASH = compute_nfo_hash(nfo_path)
    CACHED_HASH = cache.get(str_video_path, {}).get("nfo_hash")
    if CACHED_HASH == nfo_hash and not config.get("always_apply_nfo", True):
        # NFO는 적용 안 함
        logging.info(f"Skipped unchanged NFO: {nfo_path}")

        # 삭제 옵션이 켜져 있으면 삭제
        if delete_nfo_after_apply:
            try:
                nfo_path.unlink()
                logging.info(f"Deleted unchanged NFO: {nfo_path}")
            except Exception as e:
                logging.warning(f"Failed to delete NFO file: {nfo_path} - {e}")
        return False

    # Plex 아이템 찾기
    ratingKey = cache.get(str_video_path, {}).get("ratingKey")
    PLEX_ITEM = None
    if ratingKey:
        try:
            PLEX_ITEM = plex.fetchItem(ratingKey)
        except Exception:
            PLEX_ITEM = None

    if not plex_item:
        PLEX_ITEM = find_plex_item(str_video_path)
        if plex_item:
            update_cache(str_video_path, ratingKey=plex_item.ratingKey)
        else:
            logging.warning(f"[WARN] Plex item not found for {str_video_path}")
            return False

    # NFO 적용
    SUCCESS = apply_nfo(plex_item, str_video_path)
    if success:
        update_cache(str_video_path, ratingKey=plex_item.ratingKey, NFO_HASH=nfo_hash)

        # NFO 삭제 옵션
        if delete_nfo_after_apply:
            try:
                nfo_path.unlink()
                if DETAIL:
                    logging.debug(f"[-] Deleted NFO: {nfo_path}")
            except Exception as e:
                logging.warning(f"[WARN] Failed to delete NFO file: {nfo_path} - {e}")

    return success

# ==============================
# 파일 처리 통합 (영상 + NFO)
# ==============================
PROCESSED_FILES = set()
WATCH_DEBOUNCE_DELAY = config.get("watch_debounce_delay", 2)
FILE_QUEUE = queue.Queue()

def process_file(file_path):
    logging.debug(f"[PROCESS_FILE] Start: {file_path}")
    ABS_PATH = Path(file_path).resolve()
    STR_PATH = str(abs_path)

    # 이미 처리된 파일이면 skip
    if str_path in processed_files:
        return False
    processed_files.add(str_path)

    PLEX_ITEM = None

    # 영상 파일 처리
    if abs_path.suffix.lower() in VIDEO_EXTS:
        ratingKey = cache.get(str_path, {}).get("ratingKey")
        if ratingKey:
            try:
                PLEX_ITEM = plex.fetchItem(ratingKey)
            except Exception:
                pass
        if not plex_item:
            PLEX_ITEM = find_plex_item(str_path)
            if plex_item:
                update_cache(str_path, ratingKey=plex_item.ratingKey)

    # NFO 파일 처리 → 확실히 .nfo만
    if abs_path.suffix.lower() == ".nfo":
        process_nfo(str_path)

    # 자막 처리
    if subtitles_enabled and abs_path.suffix.lower() in VIDEO_EXTS and plex_item:
        SRT_FILES = extract_subtitles(str_path)
        if srt_files:
            upload_subtitles(plex_item, srt_files)

    return True

# ==============================
# Subtitle extraction & upload
# ==============================
def extract_subtitles(video_path):
    base, _ = os.path.splitext(video_path)
    SRT_FILES=[]
    try:
        RESULT=subprocess.run([str(FFPROBE_BIN),"-v","error","-select_streams","s",
                               "-show_entries","STREAM=index:STREAM_TAGS=language,codec_name",
                               "-of","json",video_path],
                              CAPTURE_OUTPUT=True,TEXT=True,CHECK=True)
        STREAMS=json.loads(result.stdout).get("streams",[])
        for s in streams:
            IDX=s.get("index")
            CODEC=s.get("codec_name","")
            if codec.lower() in ["pgs","dvdsub","hdmv_pgs","vobsub"]:
                logging.warning(f"Skipping unsupported subtitle codec {codec} in {video_path}")
                continue
            LANG=map_lang(s.get("tags",{}).get("language","und"))
            SRT=f"{base}.{lang}.srt"
            if os.path.exists(srt): continue
            subprocess.run([str(FFMPEG_BIN),"-y","-i",video_path,"-map",f"0:s:{idx}",srt],
                           STDOUT=subprocess.DEVNULL,STDERR=subprocess.DEVNULL,CHECK=True)
            srt_files.append((srt,lang))
    except Exception as e:
        logging.error(f"[ERROR] Subtitle extraction failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep,srt_files):
    for srt,lang in srt_files:
        RETRIES=3
        while retries>0:
            try:
                with api_semaphore:
                    # plexapi may provide different method names; try common ones
                    if hasattr(ep, "uploadSubtitles"):
                        ep.uploadSubtitles(srt,LANGUAGE=lang)
                    elif hasattr(ep, "addSubtitles"):
                        ep.addSubtitles(srt, LANGUAGE=lang)
                    else:
                        # fallback: try library-level upload (not ideal)
                        try:
                            ep.uploadSubtitles(srt, LANGUAGE=lang)
                        except Exception:
                            raise
                    time.sleep(request_delay)
                break
            except Exception as e:
                retries-=1
                logging.error(f"[ERROR] Subtitle upload failed: {srt} - {e}, retries left: {retries}")

# ==============================
# processed_files prune 기능
# ==============================
def prune_processed_files(MAX_SIZE=10000):
    """
    processed_files가 너무 커지면 오래된 항목 제거
    """
    if len(processed_files) > max_size:
        TO_REMOVE = list(processed_files)[:len(processed_files)-max_size]
        for f in to_remove:
            processed_files.remove(f)
        logging.debug(f"[PRUNE] processed_files pruned {len(to_remove)} entries")

# ==============================
# Watchdog 이벤트 처리 (통합 + debounce + retry)
# ==============================
class VideoEventHandler(FileSystemEventHandler):
    def __init__(self, NFO_WAIT=10, VIDEO_WAIT=2, DEBOUNCE_DELAY=2):
        self.NFO_QUEUE = set()
        self.VIDEO_QUEUE = set()
        self.NFO_TIMER = None
        self.VIDEO_TIMER = None
        self.NFO_WAIT = nfo_wait
        self.VIDEO_WAIT = video_wait
        self.LOCK = threading.Lock()
        self.RETRY_QUEUE = {}  # {nfo_path: [next_retry_time, retry_count]}
        self.LAST_EVENT_TIMES = {}
        self.DEBOUNCE_DELAY = debounce_delay

    def _should_process(self, path):
        EXT = Path(path).suffix.lower()
        if ext not in VIDEO_EXTS + (".nfo",):
            return False
        if "/@eaDir/" in path or "/.DS_Store" in path or Path(path).name.startswith("."):
            return False
        return True

    def _enqueue_with_debounce(self, path, queue_set, timer_attr, wait_time):
        NOW = time.time()
        LAST_TIME = self.last_event_times.get(path, 0)
        if now - last_time < self.debounce_delay:
            return
        self.last_event_times[path] = now

        with self.lock:
            queue_set.add(path)
            if getattr(self, timer_attr) is None:
                T = threading.Timer(wait_time, getattr(self, f"process_{timer_attr}_queue"))
                setattr(self, timer_attr, t)
                t.start()
            logging.debug(f"[WATCHDOG] Scheduled processing: {path}")

    def on_any_event(self, event):
        if event.is_directory:
            return
        PATH = str(Path(event.src_path).resolve())
        if not self._should_process(path):
            # rename 후 .nfo인 경우 처리
            if event.EVENT_TYPE == "moved" and path.lower().endswith(".nfo"):
                self._enqueue_with_debounce(path, self.nfo_queue, "nfo_timer", self.nfo_wait)
            else:
                logging.debug(f"[WATCHDOG] Skipped non-target/system file: {path}")
            return
        EXT = Path(path).suffix.lower()
        if EXT == ".nfo":
            self._enqueue_with_debounce(path, self.nfo_queue, "nfo_timer", self.nfo_wait)
        elif ext in VIDEO_EXTS:
            self._enqueue_with_debounce(path, self.video_queue, "video_timer", self.video_wait)

    # -----------------------------
    # Queue 처리
    # -----------------------------
    def process_nfo_timer_queue(self):
        with self.lock:
            NFO_FILES = list(self.nfo_queue)
            self.nfo_queue.clear()
            self.NFO_TIMER = None
        for nfo_path in nfo_files:
            SUCCESS = process_nfo(nfo_path)  # ← NFO 경로만 전달
            if not success:
                self.retry_queue[str(nfo_path)] = [time.time() + 5, 1]
        self._process_retry_queue()

    def process_video_timer_queue(self):
        with self.lock:
            VIDEO_FILES = list(self.video_queue)
            self.video_queue.clear()
            self.VIDEO_TIMER = None
        for video_path in video_files:
            # 영상 파일만 처리할 경우, 내부에서 NFO 찾도록 process_nfo 호출
            SUCCESS = process_nfo(Path(video_path).with_suffix(".nfo"))
            if not success:
                NFO_PATH = str(Path(video_path).with_suffix(".nfo"))
                self.retry_queue[nfo_path] = [time.time() + 5, 1]
        self._process_retry_queue()

    # -----------------------------
    # Retry 처리
    # -----------------------------
    def _process_retry_queue(self):
        NOW = time.time()
        for nfo_path, (retry_time, count) in list(self.retry_queue.items()):
            if now >= retry_time:
                SUCCESS = process_nfo(nfo_path)
                if success:
                    del self.retry_queue[nfo_path]
                elif count < 3:
                    self.retry_queue[nfo_path] = [now + 5, count + 1]
                else:
                    logging.warning(f"[WATCHDOG] Failed 3 times: {nfo_path}")
                    del self.retry_queue[nfo_path]

# ==============================
# Scan: NFO 전용 (신규)
# ==============================
def scan_nfo_files(base_dirs):
    NFO_FILES = []
    for base_dir in base_dirs:
        for root, _, files in os.walk(base_dir):
            for f in files:
                if f.lower().endswith(".nfo"):
                    nfo_files.append(os.path.abspath(os.path.join(root, f)))
    if DETAIL: logging.debug(f"[SCAN] Found {len(nfo_files)} NFO files")
    return nfo_files

# ==============================
# Scan and update cache
# ==============================
def scan_and_update_cache(base_dirs):
    """
    1) 영상 파일 스캔
    2) 캐시와 비교하여 누락/삭제 반영
    """
    global cache
    EXISTING_FILES = set(cache.keys())
    CURRENT_FILES = set()

    TOTAL_FILES = 0
    for base_dir in base_dirs:
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                ABS_PATH = os.path.abspath(os.path.join(root, f))
                if not abs_path.lower().endswith(VIDEO_EXTS):
                    continue
                total_files += 1
                current_files.add(abs_path)

                # 캐시에 없으면 Plex 아이템 찾아 등록
                if abs_path not in cache or cache.get(abs_path) is None:
                    PLEX_ITEM = find_plex_item(abs_path)
                    if plex_item:
                        update_cache(abs_path, ratingKey=plex_item.ratingKey)

    # 삭제된 파일 캐시에서 제거
    REMOVED = existing_files - current_files
    for f in removed:
        cache.pop(f, None)

    logging.info(f"[SCAN] Completed scan. Total video files found: {total_files}")
    save_cache()

# ==============================
# Main NFO 처리 루프
# ==============================
def process_all_nfo(base_dirs):
    """
    base_dirs 내 모든 NFO 처리
    """
    NFO_FILES = []
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
            logging.error(f"[NFO] Error processing {nfo_file}: {e}", EXC_INFO=True)

# ==============================
# 메인 실행
# ==============================
def main():
    setup_ffmpeg()

    BASE_DIRS = []
    for lib_id in config.get("plex_library_ids", []):
        try:
            SECTION = plex.library.sectionByID(lib_id)
        except Exception:
            continue
        base_dirs.extend(getattr(section, "locations", []))

    if DISABLE_WATCHDOG:
        scan_and_update_cache(base_dirs)
        VIDEO_FILES = [f for f in cache.keys() if Path(f).suffix.lower() in VIDEO_EXTS]
        NFO_FILES = scan_nfo_files(base_dirs)

        with ThreadPoolExecutor(MAX_WORKERS=threads) as executor:
            for nfo in nfo_files:
                executor.submit(process_nfo, nfo)
            FUTURES = {executor.submit(process_file, f): f for f in video_files}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    logging.error(f"[MAIN] Failed: {futures[fut]} - {e}")

        save_cache()

    elif config.get("watch_folders", False):
        OBSERVER = Observer()
        HANDLER = VideoEventHandler(DEBOUNCE_DELAY=watch_debounce_delay)
        for d in base_dirs:
            observer.schedule(handler, d, RECURSIVE=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    logging.info("END")

if __NAME__=="__main__":
    main()
