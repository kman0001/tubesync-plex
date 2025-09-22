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

with CONFIG_FILE.open("r", encoding="utf-8") as f:
    config = json.load(f)

api_semaphore = threading.Semaphore(config.get("max_concurrent_requests", 2))
request_delay = config.get("request_delay", 0.1)
threads = config.get("threads", 4)

processed_files = set()
watch_debounce_delay = config.get("watch_debounce_delay", 2)
cache_modified = False
file_queue = queue.Queue()

delete_nfo_after_apply = config.get("delete_nfo_after_apply", True)
subtitles_enabled = config.get("subtitles", False)

LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr","spa":"es",
            "ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}
def map_lang(code): return LANG_MAP.get(code.lower(),"und")

# ==============================
# Default config
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
    "silent": false,
    "detail": false,
    "subtitles": false,
    "always_apply_nfo": true,
    "threads": 8,
    "max_concurrent_requests": 4,
    "request_delay": 0.2,
    "watch_folders": true,
    "watch_debounce_delay": 3,
    "delete_nfo_after_apply": true
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
# Cache handling (영상 기준으로 통합)
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

    env = os.environ.copy()
    env["PATH"] = f"{FFMPEG_BIN.parent}:{env.get('PATH','')}"
    # 예: subprocess.run([...], env=env)

    if DETAIL: logging.info("FFmpeg installed/updated successfully")

# ==============================
# Plex helpers
# ==============================
def find_plex_item(abs_path):
    abs_path = os.path.abspath(abs_path)
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception: continue

        section_type = getattr(section, "TYPE", "").lower()
        if section_type == "show": results = section.search(libtype="episode")
        elif section_type in ("movie", "video"): results = section.search(libtype="movie")
        else: continue

        for item in results:
            for part in getattr(item, "iterParts", lambda: [])():
                try:
                    if os.path.abspath(part.file) == abs_path:
                        return item
                except Exception: continue
    return None

# ==============================
# NFO process
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

def process_nfo(nfo_file):
    abs_path = Path(nfo_file).resolve()
    if not abs_path.exists():
        return False

    # 대응 영상 찾기
    video_path = abs_path.with_suffix(".mkv")
    if not video_path.exists():
        for ext in VIDEO_EXTS:
            candidate = abs_path.with_suffix(ext)
            if candidate.exists():
                video_path = candidate
                break
    if not video_path.exists():
        logging.warning(f"[NFO] Video not found for {nfo_file}")
        return False

    str_video_path = str(video_path)
    nfo_hash = compute_nfo_hash(abs_path)
    cached_hash = cache.get(str_video_path, {}).get("nfo_hash")
    if cached_hash == nfo_hash and not config.get("always_apply_nfo", True):
        if DETAIL: logging.debug(f"[NFO] Skipped (unchanged): {nfo_file}")
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
            logging.warning(f"[NFO] Plex item not found for {str_video_path}")
            return False

    # NFO 메타 적용
    apply_nfo_metadata(plex_item, abs_path)
    update_cache(str_video_path, ratingKey=plex_item.ratingKey, nfo_hash=nfo_hash)

    # NFO 삭제 옵션
    if delete_nfo_after_apply:
        try:
            abs_path.unlink()
            if DETAIL: logging.debug(f"[NFO] Deleted NFO: {abs_path}")
        except Exception as e:
            logging.warning(f"[NFO] Failed to delete {abs_path}: {e}")

    return True

def apply_nfo_metadata(ep, nfo_path):
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # 편집할 메타데이터
        edit_kwargs = {}
        locked_fields = []

        if (title := root.findtext("title")):
            edit_kwargs["title"] = title
            locked_fields.append("title")
        if (plot := root.findtext("plot")):
            edit_kwargs["summary"] = plot
            locked_fields.append("summary")
        if (aired := root.findtext("aired") or root.findtext("released")):
            edit_kwargs["originallyAvailableAt"] = aired
            locked_fields.append("originallyAvailableAt")
        if (titleSort := root.findtext("titleSort")):
            edit_kwargs["titleSort"] = titleSort
            locked_fields.append("titleSort")

        if locked_fields:
            edit_kwargs["lockedFields"] = locked_fields
            ep.edit(**edit_kwargs)  # 한 번에 잠그면서 적용

        # Thumb 처리
        if (thumb := root.findtext("thumb")):
            thumb_path = Path(thumb)
            try:
                if thumb.startswith("http"):
                    # URL poster
                    resp = requests.get(thumb, stream=True)
                    if resp.status_code == 200:
                        tmp_file = Path("/tmp/plex_thumb.jpg")
                        with open(tmp_file, "wb") as f:
                            for chunk in resp.iter_content(1024): f.write(chunk)
                        ep.uploadPoster(str(tmp_file))
                        tmp_file.unlink()
                elif thumb_path.exists():
                    # 로컬 파일 poster
                    ep.uploadPoster(str(thumb_path.resolve()))
            except Exception as e:
                logging.warning(f"[NFO] Failed to apply thumb {thumb}: {e}")

        if DETAIL:
            logging.debug(f"[NFO] Applied metadata to {ep}: {edit_kwargs}")

        return True
    except Exception as e:
        logging.error(f"[NFO] Failed to apply NFO {nfo_path} - {e}", exc_info=True)
        return False

# ==============================
# 파일 처리 통합 (영상 + NFO)
# ==============================
def process_file(file_path):
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
                    ep.uploadSubtitles(srt,language=lang)
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
# Watchdog 이벤트 처리 (통합 개선 + debounce)
# ==============================
last_event_times = {}  # 경로별 마지막 이벤트 시간

def enqueue_with_debounce(path, delay=watch_debounce_delay):
    now = time.time()
    last_time = last_event_times.get(path, 0)
    if now - last_time > delay:
        file_queue.put(path)
    last_event_times[path] = now

class WatchHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory: 
            return
        enqueue_with_debounce(str(Path(event.src_path).resolve()))

    def on_modified(self, event):
        if event.is_directory: 
            return
        enqueue_with_debounce(str(Path(event.src_path).resolve()))

    def on_deleted(self, event):
        if event.is_directory: 
            return
        abs_path = str(Path(event.src_path).resolve())
        with cache_lock:
            cache.pop(abs_path, None)
        processed_files.discard(abs_path)
        logging.info(f"[WATCHDOG] File deleted: {abs_path}")

def watch_worker(stop_event):
    while not stop_event.is_set():
        try:
            path = file_queue.get(timeout=0.5)
            process_file(path)
            prune_processed_files()
        except queue.Empty:
            continue

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
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception: continue
        base_dirs.extend(getattr(section, "locations", []))

    if DISABLE_WATCHDOG:
        scan_and_update_cache(base_dirs)
        video_files = [f for f in cache.keys() if Path(f).suffix.lower() in VIDEO_EXTS]
        nfo_files = scan_nfo_files(base_dirs)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            for nfo in nfo_files: executor.submit(process_nfo, nfo)
            futures = {executor.submit(process_file, f): f for f in video_files}
            for fut in as_completed(futures):
                try: fut.result()
                except Exception as e: logging.error(f"[MAIN] Failed: {futures[fut]} - {e}")

        save_cache()

    elif config.get("watch_folders", False):
        stop_event = threading.Event()
        observer = Observer()
        for d in base_dirs:
            observer.schedule(WatchHandler(), d, recursive=True)
        observer.start()
        watch_thread = threading.Thread(target=watch_worker, args=(stop_event,))
        watch_thread.start()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            stop_event.set()
            observer.stop()
        observer.join()
        watch_thread.join()

    logging.info("END")

if __name__=="__main__":
    main()
