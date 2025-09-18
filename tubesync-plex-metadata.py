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
# Global flags
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
        "watch_debounce_delay": "Debounce time (sec) before processing events",
        "delete_nfo_after_apply": "True = remove NFO file after applying"
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
    "delete_nfo_after_apply": True
}

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

delete_nfo_after_apply = config.get("delete_nfo_after_apply", True)
subtitles_enabled = config.get("subtitles", False)

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
        debug_http=DEBUG_HTTP  # 여기서 독립 옵션 적용
    )
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
processed_files = set()
watch_debounce_delay = config.get("watch_debounce_delay", 2)
cache_modified = False
file_queue = queue.Queue()

LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr","spa":"es",
            "ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}
def map_lang(code): return LANG_MAP.get(code.lower(),"und")

# ==============================
# Cache handling
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

def update_cache(path, ratingKey=None, nfo_hash=None):
    global cache_modified
    path = str(path)
    with cache_lock:
        current = cache.get(path, {})
        if ratingKey: current["ratingKey"] = ratingKey
        if nfo_hash: current["nfo_hash"] = nfo_hash
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
        logging.error(f"Unsupported arch: {arch}")
        sys.exit(1)

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
        r = requests.get(url, stream=True)
        r.raise_for_status()
        with open(tar_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        logging.error(f"Failed to download FFmpeg: {e}")
        sys.exit(1)

    if remote_md5:
        h = hashlib.md5()
        with open(tar_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        if h.hexdigest() != remote_md5:
            logging.error("Downloaded FFmpeg MD5 mismatch, aborting")
            sys.exit(1)

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
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    os.environ["PATH"] = f"{FFMPEG_BIN.parent}:{os.environ.get('PATH','')}"
    if DETAIL: logging.info("FFmpeg installed/updated successfully")

# -----------------------------
# Plex helpers
# -----------------------------
def find_plex_item(abs_path):
    abs_path = str(Path(abs_path).resolve())
    logging.debug(f"[FIND_PLEX_ITEM] Searching Plex item for: {abs_path}")

    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception as e:
            logging.warning(f"[FIND_PLEX_ITEM] Failed to access library ID {lib_id}: {e}")
            continue

        # 라이브러리 타입에 관계없이 검색
        try:
            if getattr(section, "TYPE", "").lower() == "show":
                results = section.search(libtype="episode")
            else:
                # movie / video / 기타
                results = section.search(libtype="movie")
        except Exception as e:
            logging.warning(f"[FIND_PLEX_ITEM] Failed to search items in library ID {lib_id}: {e}")
            continue

        for item in results:
            # parts 속성과 iterParts() 모두 체크
            parts = getattr(item, "parts", None)
            if parts is None:
                parts = getattr(item, "iterParts", lambda: [])()
            for part in parts:
                try:
                    part_path = str(Path(part.file).resolve())
                    if part_path == abs_path:
                        logging.debug(f"[FIND_PLEX_ITEM] Found item: {item.title} (ratingKey={item.ratingKey})")
                        return item
                except Exception as e:
                    logging.warning(f"[FIND_PLEX_ITEM] Failed to resolve part path: {e}")

    logging.warning(f"[FIND_PLEX_ITEM] No Plex item found for: {abs_path}")
    return None

# ==============================
# NFO handling
# ==============================
def compute_nfo_hash(nfo_path):
    h = hashlib.sha256()
    with open(nfo_path,"rb") as f:
        for chunk in iter(lambda:f.read(4096),b""): h.update(chunk)
    return h.hexdigest()

def apply_nfo(ep, file_path):
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size==0: return False
    nfo_hash = compute_nfo_hash(nfo_path)
    cached_hash = cache.get(file_path, {}).get("nfo_hash")
    if not config.get("always_apply_nfo", False) and cached_hash==nfo_hash:
        if detail: logging.info(f"NFO unchanged: {nfo_path}")
        return False
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        ep.editTitle(root.findtext("title",""), locked=True)
        ep.editSummary(root.findtext("plot",""), locked=True)
        ep.editSortTitle(root.findtext("aired",""), locked=True)
        update_cache(file_path, ep.ratingKey, nfo_hash)
        if delete_nfo_after_apply:
            try: nfo_path.unlink()
            except: pass
        return True
    except Exception as e:
        logging.error(f"Error applying NFO {nfo_path}: {e}")
        return False

# ==============================
# Subtitle extraction & upload
# ==============================
def extract_subtitles(video_path):
    base, _ = os.path.splitext(video_path)
    srt_files=[]
    try:
        result=subprocess.run([str(FFMPEG_BIN.parent/"ffprobe"),"-v","error","-select_streams","s",
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
            try:
                subprocess.run([str(FFMPEG_BIN),"-y","-i",video_path,"-map",f"0:s:{idx}",srt],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
                srt_files.append((srt,lang))
            except Exception as e:
                logging.error(f"[ERROR] Subtitle extraction failed for stream {idx} in {video_path} - {e}")
    except Exception as e:
        logging.error(f"[ERROR] ffprobe failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep,srt_files):
    for srt,lang in srt_files:
        retries=3
        while retries>0:
            try:
                with api_semaphore:
                    ep.uploadSubtitles(srt,language=lang)
                    time.sleep(request_delay)
                break
            except Exception as e:
                retries-=1
                logging.error(f"[ERROR] Subtitle upload failed: {srt} - {e}, retries left: {retries}")

# ==============================
# File processing (with debug)
# ==============================
def process_file(file_path):
    abs_path = Path(file_path).resolve()
    str_path = str(abs_path)
    logging.debug(f"[PROCESS_FILE] Start processing: {str_path}")

    if str_path in processed_files:
        logging.debug(f"[PROCESS_FILE] Already processed: {str_path}")
        return False

    if abs_path.suffix.lower() not in VIDEO_EXTS:
        logging.debug(f"[PROCESS_FILE] Skipped (not video): {str_path}")
        return False

    # Plex item 가져오기
    ratingKey = cache.get(str_path, {}).get("ratingKey")
    plex_item = None
    if ratingKey:
        try:
            plex_item = plex.fetchItem(ratingKey)
            logging.debug(f"[PROCESS_FILE] Fetched Plex item by ratingKey: {ratingKey}")
        except Exception as e:
            logging.warning(f"[PROCESS_FILE] Failed to fetch item by ratingKey {ratingKey}: {e}")

    if not plex_item:
        plex_item = find_plex_item(str_path, plex)

    if plex_item:
        update_cache(str_path, plex_item.ratingKey)
    else:
        logging.warning(f"[PROCESS_FILE] Plex item not found: {str_path}")
        processed_files.add(str_path)
        return False

    success = False
    nfo_path = abs_path.with_suffix(".nfo")
    if nfo_path.exists() and nfo_path.stat().st_size > 0:
        try:
            success = apply_nfo(plex_item, str_path)
            logging.info(f"[PROCESS_FILE] NFO applied: {str_path}")
        except Exception as e:
            logging.error(f"[PROCESS_FILE] Failed to apply NFO for {str_path}: {e}")

    if subtitles_enabled:
        try:
            srt_files = extract_subtitles(str_path)
            if srt_files:
                upload_subtitles(plex_item, srt_files)
        except Exception as e:
            logging.error(f"[PROCESS_FILE] Subtitle extraction/upload failed for {str_path}: {e}")

    processed_files.add(str_path)
    return success

# ==============================
# Watchdog
# ==============================
class WatchHandler(FileSystemEventHandler):
    def on_any_event(self,event):
        if event.is_directory: return
        file_queue.put(str(Path(event.src_path).resolve()))

def watch_worker(stop_event):
    while not stop_event.is_set():
        try:
            path=file_queue.get(timeout=0.5)
            process_file(path)
        except queue.Empty:
            continue

# ==============================
# Scan Plex libraries + update cache
# ==============================
def scan_and_update_cache(base_dirs):
    """
    Scan Plex libraries, add missing meta IDs, remove deleted files.
    base_dirs: list of directories to scan
    """
    global cache
    existing_files = set(cache.keys())
    all_files = []

    # 모든 파일 수집
    for base_dir in base_dirs:
        for root, dirs, files in os.walk(base_dir):
            for f in files:
                all_files.append(os.path.join(root, f))

    current_files = set()
    total_files = 0

    for f in all_files:
        abs_path = os.path.abspath(f)
        if not f.lower().endswith(VIDEO_EXTS):
            continue
        total_files += 1
        current_files.add(abs_path)

        # 캐시에 없으면 Plex 아이템 찾아서 등록
        if abs_path not in cache or cache.get(abs_path) is None:
            plex_item = find_plex_item(abs_path)
            if plex_item:
                cache[abs_path] = plex_item.ratingKey
                processed_files.add(abs_path)  # <<< 캐시 등록 시 processed_files에도 추가

    # 삭제된 파일 캐시에서 제거
    removed = existing_files - current_files
    for f in removed:
        cache.pop(f, None)
        if f in processed_files:
            processed_files.remove(f)

    logging.info(f"[SCAN] Completed scan. Total video files found: {total_files}")
    try:
        save_cache()
        logging.info("[SCAN] Cache updated successfully")
    except Exception as e:
        logging.error(f"[SCAN] Failed to save cache: {e}")

# ==============================
# Main function
# ==============================
def main():
    setup_ffmpeg()

    # ----------------------
    # scan_and_update_cache()용 base_dirs 준비
    # ----------------------
    base_dirs = []
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception as e:
            logging.warning(f"Failed to access Plex library ID {lib_id}: {e}")
            continue
        for loc in getattr(section, "locations", []):
            base_dirs.append(loc)

    # ----------------------
    # 캐시 업데이트용 스캔
    # ----------------------
    scan_and_update_cache(base_dirs)

    # ----------------------
    # 개별 파일 처리
    # ----------------------
    video_files = list(processed_files)  # scan 과정에서 processed_files에 추가됨
    logging.info(f"[INFO] Total video files found: {len(video_files)}")

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(process_file, f): f for f in video_files}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logging.error(f"[ERROR] Processing {futures[fut]} failed: {e}")

    save_cache()

    # ----------------------
    # Watchdog
    # ----------------------
    if config.get("watch_folders", False) and not DISABLE_WATCHDOG:
        stop_event = threading.Event()
        observer = Observer()
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except:
                continue
            for loc in getattr(section, "locations", []):
                observer.schedule(WatchHandler(), loc, recursive=True)
        observer.start()
        watch_thread = threading.Thread(target=watch_worker, args=(stop_event,))
        watch_thread.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            stop_event.set()
            observer.stop()
        observer.join()
        watch_thread.join()

    logging.info("END")

if __name__=="__main__":
    main()
