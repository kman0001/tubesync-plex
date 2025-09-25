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

# Language mapping for SUBTITLES
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
        "ALWAYS_APPLY_NFO": "true = always apply NFO metadata regardless of hash",
        "THREADS": "Number of worker THREADS for initial scanning",
        "MAX_CONCURRENT_REQUESTS": "Max concurrent Plex API requests",
        "REQUEST_DELAY": "Delay between Plex API requests (sec)",
        "WATCH_FOLDERS": "true = enable real-time folder monitoring",
        "WATCH_DEBOUNCE_DELAY": "Debounce time (sec) before processing events",
        "DELETE_NFO_AFTER_APPLY": "true = remove NFO file after applying"
    },
    "PLEX_BASE_URL": "",
    "PLEX_TOKEN": "",
    "PLEX_LIBRARY_IDS": [],
    "SILENT": False,
    "DETAIL": False,
    "SUBTITLES": False,
    "ALWAYS_APPLY_NFO": True,
    "THREADS": 8,
    "MAX_CONCURRENT_REQUESTS": 4,
    "REQUEST_DELAY": 0.2,
    "WATCH_FOLDERS": True,
    "WATCH_DEBOUNCE_DELAY": 3,
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

# Config → 전역 변수
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

# 기존 핸들러 제거
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# 로그 레벨 결정
if args.debug:
    log_level = logging.DEBUG        # --debug
elif SILENT:
    log_level = logging.WARNING      # 요약 모드
else:
    log_level = logging.INFO         # 일반 로그

logging.basicConfig(
    level=log_level,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True
)

# HTTP debug 로그 별도 설정
if not DEBUG_HTTP:
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

# ==============================
# 로그 출력 함수
# ==============================
def log_detail(msg):
    """ DETAIL 전용 로그 """
    if DETAIL and not SILENT:
        logging.info(f"[DETAIL] {msg}")

def log_debug(msg):
    """ DEBUG 전용 로그 """
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
# Connect Plex
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
# Cache handling (영상 기준으로 통합)
# ==============================
if CACHE_FILE.exists():
    with CACHE_FILE.open("r", encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}

cache_modified = False

def save_cache():
    global cache_modified
    with cache_lock:
        if cache_modified:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            logging.info(f"[CACHE] Saved to {CACHE_FILE}")
            cache_modified = False

def update_cache(video_path, ratingKey=None, nfo_hash=None):
    global cache_modified
    path = str(video_path)
    with cache_lock:
        current = cache.get(path, {})
        if ratingKey: current["ratingKey"] = ratingKey
        if nfo_hash: current["nfo_hash"] = nfo_hash
        cache[path] = current
        cache_modified = True
        if DETAIL:
            logging.debug(f"[CACHE] update_cache: {path} => {current}")

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
        return  # 더 이상 강제 종료하지 않음

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
        logging.info("FFmpeg up-to-date (MD5 match)")
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
# NFO Process (titleSort 안전 적용)
# ==============================
def compute_nfo_hash(nfo_path):
    try:
        with open(nfo_path, "rb") as f:
            data = f.read()
        h = hashlib.md5(data).hexdigest()
        if DETAIL:
            logging.debug(f"[NFO] compute_nfo_hash: {nfo_path} -> {h}")
        return h
    except Exception as e:
        logging.error(f"[NFO] compute_nfo_hash failed: {nfo_path} - {e}")
        return None

def safe_edit(ep, title=None, summary=None, aired=None):
    """
    일반 필드(title, summary, aired) 편집
    """
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
    """
    NFO를 Plex 아이템에 적용
    - titleSort가 없으면 title로 대체
    - editSortTitle 사용으로 첫 글자 손실 방지
    """
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False

    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title", "").strip() or None
        plot = root.findtext("plot", "").strip() or None
        aired = root.findtext("aired", "").strip() or None
        title_sort = root.findtext("titleSort", "").strip() or title  # NFO 없으면 title 사용

        if DETAIL:
            logging.debug(f"[-] Applying NFO: {file_path} -> {title}")

        # 일반 필드 적용
        safe_edit(ep, title=title, summary=plot, aired=aired)

        # titleSort는 editSortTitle로 적용
        if title_sort:
            try:
                ep.editSortTitle(title_sort, locked=True)  # 첫 글자 손실 없음
            except Exception:
                # fallback: metadata.edit 사용
                ep.edit(**{"titleSort.value": title_sort, "titleSort.locked": 1})
            ep.reload()

        return True

    except Exception as e:
        logging.error(f"[!] Error applying NFO {nfo_path}: {e}", exc_info=True)
        return False

def process_nfo(file_path):
    """
    NFO 처리 (캐시 기반 + ALWAYS_APPLY_NFO 옵션 반영)
    """
    p = Path(file_path)
    if p.suffix.lower() == ".nfo":
        nfo_path = p
        video_path = p.with_suffix("")  # 영상 파일 추정
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
    cached_hash = cache.get(str_video_path, {}).get("nfo_hash")

    # 🔹 캐시 해시가 동일해도 ALWAYS_APPLY_NFO가 True면 적용
    if cached_hash == nfo_hash and not ALWAYS_APPLY_NFO:
        logging.info(f"[CACHE] NFO already applied for video: {str_video_path}")
        if DELETE_NFO_AFTER_APPLY:
            try: nfo_path.unlink()
            except: pass
        return False

    # Plex 아이템 조회
    plex_item = None
    ratingKey = cache.get(str_video_path, {}).get("ratingKey")
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
            return False

    # NFO 적용
    success = apply_nfo(plex_item, str_video_path)
    if success:
        update_cache(str_video_path, ratingKey=plex_item.ratingKey, nfo_hash=nfo_hash)
        if DELETE_NFO_AFTER_APPLY:
            try: nfo_path.unlink()
            except: pass

    return success

# ==============================
# 파일 처리 통합 (영상 + NFO)
# ==============================
processed_files = set()
file_queue = queue.Queue()

def process_file(file_path):
    """
    단일 파일 처리 (영상 또는 NFO)
    - NFO는 캐시 기반으로만 Plex 적용
    - 영상 파일이면 캐시 존재 시 Plex 호출 생략
    """
    abs_path = Path(file_path).resolve()
    str_path = str(abs_path)

    if str_path in processed_files:
        return False
    processed_files.add(str_path)

    plex_item = None
    if abs_path.suffix.lower() in VIDEO_EXTS:
        ratingKey = cache.get(str_path, {}).get("ratingKey")
        if ratingKey:
            try:
                plex_item = plex.fetchItem(ratingKey)
            except Exception:
                plex_item = None
        if not plex_item:
            plex_item = find_plex_item(str_path)
            if plex_item:
                update_cache(str_path, ratingKey=plex_item.ratingKey)

    # NFO 처리
    if abs_path.suffix.lower() == ".nfo":
        process_nfo(str_path)
    elif abs_path.suffix.lower() in VIDEO_EXTS:
        nfo_path = abs_path.with_suffix(".nfo")
        if nfo_path.exists():
            process_nfo(str(nfo_path))

    # 자막 처리
    if SUBTITLES_ENABLED and abs_path.suffix.lower() in VIDEO_EXTS and plex_item:
        srt_files = extract_subtitles(str_path)
        if srt_files:
            upload_subtitles(plex_item, srt_files)

    return True

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
# Watchdog 이벤트 처리 (영상 + NFO 전용)
# ==============================
import threading
import time
import logging
from pathlib import Path
from watchdog.events import FileSystemEventHandler

class VideoEventHandler(FileSystemEventHandler):
    def __init__(self, nfo_wait=10, video_wait=2, debounce_delay=3):
        self.nfo_queue = set()
        self.video_queue = set()
        self.nfo_timer = {}
        self.video_timer = {}
        self.nfo_wait = nfo_wait
        self.video_wait = video_wait
        self.lock = threading.Lock()
        self.retry_queue = {}  # {nfo_path: [next_retry_time, retry_count]}
        self.debounce_delay = debounce_delay

    def _normalize_path(self, path):
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="ignore")
        return str(Path(path).resolve())

    def _should_process(self, path):
        path = self._normalize_path(path)
        ext = Path(path).suffix.lower()
        if ext not in VIDEO_EXTS + (".nfo",):
            return False
        if "/@eaDir/" in path or "/.DS_Store" in path or Path(path).name.startswith("."):
            return False
        return True

    def _enqueue(self, path, queue_set, timer_dict, wait_time, process_func):
        path = self._normalize_path(path)
        with self.lock:
            if path in queue_set:
                logging.debug(f"[WATCHDOG] Debounced (already scheduled): {path}")
                return
            queue_set.add(path)
            if path in timer_dict:
                timer_dict[path].cancel()
            t = threading.Timer(wait_time, self._process_path, args=(path, queue_set, timer_dict, process_func))
            timer_dict[path] = t
            t.start()
            logging.debug(f"[WATCHDOG] Scheduled processing: {path}")

    def _process_path(self, path, queue_set, timer_dict, process_func):
        path = self._normalize_path(path)
        with self.lock:
            queue_set.discard(path)
            timer_dict.pop(path, None)
        process_func(path)

    def on_any_event(self, event):
        if event.is_directory:
            return

        src_path = self._normalize_path(event.src_path)
        ext = Path(src_path).suffix.lower()

        if not self._should_process(src_path):
            return  # NFO나 영상 외 파일은 무시

        # -----------------------
        # NFO 파일 처리
        # -----------------------
        if ext == ".nfo":
            self._enqueue(src_path, self.nfo_queue, self.nfo_timer, self.nfo_wait, self.process_nfo)
            return

        # -----------------------
        # VIDEO 파일 처리
        # -----------------------
        if ext in VIDEO_EXTS:
            self._enqueue(src_path, self.video_queue, self.video_timer, self.video_wait, self.process_video)

    # -----------------------------
    # 실제 처리 함수
    # -----------------------------
    def process_nfo(self, nfo_path):
        nfo_path = self._normalize_path(nfo_path)
        logging.info(f"[WATCHDOG] Processing NFO: {nfo_path}")
        success = process_nfo(nfo_path)  # 외부 함수 호출
        if not success:
            with self.lock:
                self.retry_queue[nfo_path] = [time.time() + 5, 1]

    def process_video(self, video_path):
        video_path = self._normalize_path(video_path)
        logging.info(f"[WATCHDOG] Processing Video: {video_path}")
        nfo_path = Path(video_path).with_suffix(".nfo")
        if nfo_path.exists():
            self.process_nfo(str(nfo_path))

    # -----------------------------
    # Retry 처리
    # -----------------------------
    def _process_retry_queue(self):
        now = time.time()
        for nfo_path, (retry_time, count) in list(self.retry_queue.items()):
            if now >= retry_time:
                success = process_nfo(nfo_path)
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
    """
    base_dirs: list[Path] 또는 Path 단일 객체 가능
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
# Scan and update cache
# ==============================
def scan_and_update_cache(base_dirs):
    """
    1) 영상 파일 스캔
    2) 캐시와 비교하여 누락/삭제 반영
    """
    global cache
    existing_files = set(cache.keys())
    current_files = set()

    total_files = 0
    for base_dir in base_dirs:
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                abs_path = os.path.abspath(os.path.join(root, f))
                if not abs_path.lower().endswith(VIDEO_EXTS):
                    continue
                total_files += 1
                current_files.add(abs_path)

                # 캐시에 없으면 Plex 아이템 찾아 등록
                if abs_path not in cache or cache.get(abs_path) is None:
                    plex_item = find_plex_item(abs_path)
                    if plex_item:
                        update_cache(abs_path, ratingKey=plex_item.ratingKey)

    # 삭제된 파일 캐시에서 제거
    removed = existing_files - current_files
    for f in removed:
        cache.pop(f, None)

    logging.info(f"[SCAN] Completed scan. Total video files found: {total_files}")
    save_cache()

# ==============================
# Main NFO 처리 루프
# ==============================
def process_all_nfo(base_dirs):
    """
    base_dirs: list[Path] 또는 Path 단일 객체 가능
    base_dirs 내 모든 NFO 처리
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
# 메인 실행
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
        scan_and_update_cache(base_dirs)
        video_files = [f for f in cache.keys() if Path(f).suffix.lower() in VIDEO_EXTS]
        nfo_files = scan_nfo_files(BASE_DIR)

        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            for nfo in nfo_files:
                executor.submit(process_nfo, nfo)
            futures = {executor.submit(process_file, f): f for f in video_files}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    logging.error(f"[MAIN] Failed: {futures[fut]} - {e}")

        save_cache()

    elif config.get("WATCH_FOLDERS", False):
        observer = Observer()
        handler = VideoEventHandler(debounce_delay=WATCH_DEBOUNCE_DELAY)
        for d in base_dirs:
            observer.schedule(handler, d, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    logging.info("END")

if __name__=="__main__":
    main()
