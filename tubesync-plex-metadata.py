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
parser.add_argument("--detail", action="store_true", help="Enable detailed logging")
parser.add_argument("--debug-http", action="store_true", help="Enable HTTP debug logging")
parser.add_argument("--debug", action="store_true", help="Enable debug mode (implies detail logging)")
parser.add_argument("--base-dir", help="Base directory override", default=os.environ.get("BASE_DIR", str(Path(__file__).parent.resolve())))
args = parser.parse_args()

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
        "plex_base_url": "Base URL of your Plex server (e.g., http://localhost:32400).",
        "plex_token": "Your Plex authentication token.",
        "plex_library_ids": "List of Plex library IDs to sync (e.g., [10,21,35]).",
        "silent": "true = only summary logs, False = detailed logs",
        "detail": "true = verbose mode (debug output)",
        "subtitles": "true = extract and upload subtitles",
        "always_apply_nfo": "true = always apply NFO metadata regardless of hash",
        "threads": "Number of worker threads for initial scanning",
        "max_concurrent_requests": "Max concurrent Plex API requests",
        "request_delay": "Delay between Plex API requests (sec)",
        "watch_folders": "true = enable real-time folder monitoring",
        "watch_debounce_delay": "Debounce time (sec) before processing events",
        "delete_nfo_after_apply": "true = remove NFO file after applying"
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
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

with CONFIG_FILE.open("r", encoding="utf-8") as f:
    config = json.load(f)

# Apply overrides
if DISABLE_WATCHDOG:
    config["watch_folders"] = False

delete_nfo_after_apply = config.get("delete_nfo_after_apply", True)
subtitles_enabled = config.get("subtitles", False)
request_delay = config.get("request_delay", 0.1)
threads = config.get("threads", 4)
api_semaphore = threading.Semaphore(config.get("max_concurrent_requests", 2))

# ==============================
# Logging setup
# ==============================
if not DEBUG_HTTP:
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
log_level = logging.DEBUG if DETAIL else logging.INFO
logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

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
        config["plex_base_url"],
        config["plex_token"],
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
    for lib_id in config.get("plex_library_ids", []):
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
    단일 NFO 처리
    """
    p = Path(file_path)
    if p.suffix.lower() == ".nfo":
        nfo_path = p
        video_path = p.with_suffix("")  # video path 추정
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
    if cached_hash == nfo_hash and not config.get("always_apply_nfo", True):
        if DETAIL:
            logging.debug(f"[-] Skipped (unchanged): {nfo_path}")
        return False

    # Plex 아이템 찾기
    ratingKey = cache.get(str_video_path, {}).get("ratingKey")
    plex_item = None
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
processed_files = set()
watch_debounce_delay = config.get("watch_debounce_delay", 2)
file_queue = queue.Queue()

def process_file(file_path):
    logging.debug(f"[PROCESS_FILE] Start: {file_path}")
    abs_path = Path(file_path).resolve()
    str_path = str(abs_path)

    # 이미 처리된 파일이면 skip
    if str_path in processed_files:
        return False
    processed_files.add(str_path)

    plex_item = None

    # 영상 파일 처리
    if abs_path.suffix.lower() in VIDEO_EXTS:
        ratingKey = cache.get(str_path, {}).get("ratingKey")
        if ratingKey:
            try:
                plex_item = plex.fetchItem(ratingKey)
            except Exception:
                pass
        if not plex_item:
            plex_item = find_plex_item(str_path)
            if plex_item:
                update_cache(str_path, ratingKey=plex_item.ratingKey)

    # NFO 파일 처리 → 확실히 .nfo만
    if abs_path.suffix.lower() == ".nfo":
        process_nfo(str_path)

    # 자막 처리
    if subtitles_enabled and abs_path.suffix.lower() in VIDEO_EXTS and plex_item:
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
                    time.sleep(request_delay)
                break
            except Exception as e:
                retries-=1
                logging.error(f"[ERROR] Subtitle upload failed: {srt} - {e}, retries left: {retries}")

# ==============================
# processed_files prune 기능
# ==============================
def prune_processed_files(max_size=10000):
    """
    processed_files가 너무 커지면 오래된 항목 제거
    """
    if len(processed_files) > max_size:
        to_remove = list(processed_files)[:len(processed_files)-max_size]
        for f in to_remove:
            processed_files.remove(f)
        logging.debug(f"[PRUNE] processed_files pruned {len(to_remove)} entries")

# ==============================
# Watchdog 이벤트 처리 (통합 + debounce + retry)
# ==============================
class VideoEventHandler(FileSystemEventHandler):
    def __init__(self, nfo_wait=10, video_wait=2, debounce_delay=2):
        self.nfo_queue = set()
        self.video_queue = set()
        self.nfo_timer = None
        self.video_timer = None
        self.nfo_wait = nfo_wait
        self.video_wait = video_wait
        self.lock = threading.Lock()
        self.retry_queue = {}
        self.last_event_times = {}
        self.debounce_delay = debounce_delay

    def _should_process(self, path):
        ext = Path(path).suffix.lower()
        if ext not in VIDEO_EXTS + (".nfo",):
            return False
        if "/@eaDir/" in path or "/.DS_Store" in path or Path(path).name.startswith("."):
            return False
        return True

    def _enqueue_with_debounce(self, path, queue_set, timer_attr, wait_time):
        now = time.time()
        last_time = self.last_event_times.get(path, 0)
        if now - last_time < self.debounce_delay:
            return
        self.last_event_times[path] = now

        with self.lock:
            queue_set.add(path)
            if getattr(self, timer_attr) is None:
                t = threading.Timer(wait_time, getattr(self, f"process_{timer_attr}_queue"))
                setattr(self, timer_attr, t)
                t.start()
            logging.debug(f"[WATCHDOG] Scheduled processing: {path}")

    def on_any_event(self, event):
        if event.is_directory:
            return
        path = str(Path(event.src_path).resolve())
        if not self._should_process(path):
            logging.debug(f"[WATCHDOG] Skipped non-target/system file: {path}")
            return
        ext = Path(path).suffix.lower()
        if ext == ".nfo":
            self._enqueue_with_debounce(path, self.nfo_queue, "nfo_timer", self.nfo_wait)
        elif ext in VIDEO_EXTS:
            self._enqueue_with_debounce(path, self.video_queue, "video_timer", self.video_wait)

    # -----------------------------
    # Queue 처리
    # -----------------------------
    def process_nfo_timer_queue(self):
        with self.lock:
            nfo_files = list(self.nfo_queue)
            self.nfo_queue.clear()
            self.nfo_timer = None

        for nfo_path in nfo_files:
            nfo_path = str(nfo_path)
            video_path = Path(nfo_path).with_suffix(".mkv")
            if not video_path.exists():
                for e in VIDEO_EXTS:
                    candidate = Path(nfo_path).with_suffix(e)
                    if candidate.exists():
                        video_path = candidate
                        break

            if video_path.exists():
                # NFO 적용
                success = process_nfo(nfo_path, str(video_path))
                if success:
                    # 적용 후 NFO 삭제
                    if delete_nfo_after_apply:
                        try:
                            Path(nfo_path).unlink()
                            logging.debug(f"[WATCHDOG] Deleted NFO: {nfo_path}")
                        except Exception as e:
                            logging.warning(f"[WATCHDOG] Failed to delete NFO: {nfo_path} - {e}")
                else:
                    # 실패 시 재시도
                    self.retry_queue[str(video_path)] = [time.time() + 5, 1]
            else:
                logging.warning(f"[WATCHDOG] Video not found for NFO: {nfo_path}")

        # Retry 처리
        self._process_retry_queue()

    def process_video_timer_queue(self):
        with self.lock:
            video_files = list(self.video_queue)
            self.video_queue.clear()
            self.video_timer = None
        for video_path in video_files:
            success = process_file(video_path)
            if not success:
                self.retry_queue[video_path] = [time.time()+5,1]

    # -----------------------------
    # Retry 처리
    # -----------------------------
    def _process_retry_queue(self):
        now = time.time()
        for path, (retry_time, count) in list(self.retry_queue.items()):
            if now >= retry_time:
                success = process_file(path)
                if success:
                    del self.retry_queue[path]
                elif count < 3:
                    self.retry_queue[path] = [now + 5, count + 1]
                else:
                    logging.warning(f"[WATCHDOG] Failed 3 times: {path}")
                    del self.retry_queue[path]

# ==============================
# Scan: NFO 전용 (신규)
# ==============================
def scan_nfo_files(base_dirs):
    nfo_files = []
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
    base_dirs 내 모든 NFO 처리
    """
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
    for lib_id in config.get("plex_library_ids", []):
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue
        base_dirs.extend(getattr(section, "locations", []))

    if DISABLE_WATCHDOG:
        scan_and_update_cache(base_dirs)
        video_files = [f for f in cache.keys() if Path(f).suffix.lower() in VIDEO_EXTS]
        nfo_files = scan_nfo_files(base_dirs)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            for nfo in nfo_files:
                executor.submit(process_nfo, nfo)
            futures = {executor.submit(process_file, f): f for f in video_files}
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    logging.error(f"[MAIN] Failed: {futures[fut]} - {e}")

        save_cache()

    elif config.get("watch_folders", False):
        observer = Observer()
        handler = VideoEventHandler(debounce_delay=watch_debounce_delay)
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
