#!/usr/bin/env python3
import os, sys, json, time, threading, subprocess, shutil, hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty
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
parser.add_argument("--debug", action="store_true", help="Enable debug logging")
args = parser.parse_args()
DEBUG = args.debug

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

delete_nfo_after_apply = config.get("delete_nfo_after_apply", True)

# ==============================
# Logging
# ==============================
silent = config.get("silent", False)
detail = config.get("detail", False) and not silent
log_level = logging.DEBUG if DEBUG else (logging.INFO if not config.get("silent", False) else logging.WARNING)
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
            logging.debug(f"[HTTP DEBUG] REQUEST: {request.method} {request.url}")
        response = super().send(request, **kwargs)
        if self.enable_debug:
            logging.debug(f"[HTTP DEBUG] RESPONSE: {response.status_code} {response.reason}")
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
cache_modified = False

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
    if arch=="x86_64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif arch=="aarch64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else:
        logging.error(f"Unsupported arch: {arch}")
        sys.exit(1)

    md5_url = url + ".md5"
    tmp_dir = Path("/tmp/ffmpeg_dl")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tar_path = tmp_dir / "ffmpeg.tar.xz"

    # 1. 원격 MD5 가져오기
    try:
        r = requests.get(md5_url, timeout=10)
        r.raise_for_status()
        remote_md5 = r.text.strip().split()[0]
    except Exception as e:
        logging.warning(f"Failed to fetch remote MD5: {e}")
        remote_md5 = None

    # 2. 로컬 FFmpeg 최신 여부 확인
    local_md5 = FFMPEG_SHA_FILE.read_text().strip() if FFMPEG_SHA_FILE.exists() else None
    if FFMPEG_BIN.exists() and remote_md5 and local_md5 == remote_md5:
        logging.info("FFmpeg up-to-date (MD5 match)")
        return

    # 3. 로컬 파일 손상 시 삭제 후 재다운로드
    if FFMPEG_BIN.exists():
        logging.warning("Local FFmpeg MD5 mismatch, redownloading...")
        FFMPEG_BIN.unlink(missing_ok=True)
        (FFMPEG_BIN.parent / "ffprobe").unlink(missing_ok=True)

    # 4. 다운로드
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

    # 5. 다운로드 파일 MD5 검증
    if remote_md5:
        h = hashlib.md5()
        with open(tar_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        if h.hexdigest() != remote_md5:
            logging.error("Downloaded FFmpeg MD5 mismatch, aborting")
            sys.exit(1)

    # 6. 압축 해제 및 설치
    try:
        extract_dir = tmp_dir / "extract"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True)
        subprocess.run(["tar", "-xJf", str(tar_path), "-C", str(extract_dir)], check=True)
        ffmpeg_path = next(extract_dir.glob("**/ffmpeg"))
        ffprobe_path = next(extract_dir.glob("**/ffprobe"))
        shutil.move(str(ffmpeg_path), FFMPEG_BIN)
        shutil.move(str(ffprobe_path), FFMPEG_BIN.parent / "ffprobe")
        os.chmod(FFMPEG_BIN, 0o755)
        os.chmod(FFMPEG_BIN.parent / "ffprobe", 0o755)
        if remote_md5: FFMPEG_SHA_FILE.write_text(remote_md5)
    except Exception as e:
        logging.error(f"FFmpeg extraction/move failed: {e}")
        sys.exit(1)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    os.environ["PATH"] = f"{FFMPEG_BIN.parent}:{os.environ.get('PATH','')}"
    if detail: logging.info("FFmpeg installed/updated successfully")

# ==============================
# Plex helpers
# ==============================
def find_plex_item(abs_path):
    for lib_id in config["plex_library_ids"]:
        try: section = plex.library.sectionByID(lib_id)
        except: continue
        for item in section.all():
            for part in getattr(item,"iterParts",lambda: [])():
                if os.path.abspath(part.file)==abs_path:
                    return item
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
# Subtitle extraction & Plex upload with retries
# ==============================
def extract_subtitles(file_path):
    base, _ = os.path.splitext(file_path)
    srt_files=[]
    try:
        result=subprocess.run([str(FFMPEG_BIN.parent/"ffprobe"),"-v","error","-select_streams","s",
                               "-show_entries","stream=index:stream_tags=language,codec_name",
                               "-of","json",file_path],
                              capture_output=True,text=True,check=True)
        streams=json.loads(result.stdout).get("streams",[])
        for s in streams:
            idx=s.get("index")
            codec=s.get("codec_name","")
            if codec.lower() in ["pgs","dvdsub","hdmv_pgs","vobsub"]:
                logging.warning(f"Skipping unsupported subtitle codec {codec} in {file_path}")
                continue
            lang=s.get("tags",{}).get("language","und")
            srt=f"{base}.{lang}.srt"
            if os.path.exists(srt): continue
            try:
                subprocess.run([str(FFMPEG_BIN),"-y","-i",file_path,"-map",f"0:s:{idx}",srt],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
                srt_files.append((srt,lang))
            except Exception:
                logging.warning(f"Skipping failed subtitle stream idx={idx} for {file_path}")
    except Exception as e:
        logging.error(f"[ERROR] ffprobe failed: {file_path} - {e}")
    return srt_files

def upload_subtitles(ep,srt_files):
    for srt,lang in srt_files:
        for attempt in range(1,4):
            try:
                with api_semaphore:
                    ep.uploadSubtitles(srt,language=lang)
                    time.sleep(request_delay)
                break
            except Exception as e:
                logging.warning(f"[ERROR] Subtitle upload attempt {attempt} failed: {srt} - {e}")
                time.sleep(1)

# ==============================
# File processing
# ==============================
def process_single_file(file_path):
    abs_path = Path(file_path).resolve()
    str_path = str(abs_path)
    if DEBUG: logging.debug(f"[DEBUG] Start processing: {str_path}")

    if str_path in processed_files:
        if DEBUG: logging.debug(f"[DEBUG] Already processed: {str_path}")
        return False

    plex_item = find_plex_item(str_path)
    if plex_item:
        update_cache(str_path, plex_item.ratingKey)

    processed_files.add(str_path)
    success = False

    # NFO 적용
    nfo_path = abs_path.with_suffix(".nfo")
    if nfo_path.exists() and nfo_path.stat().st_size > 0 and plex_item:
        success = apply_nfo(plex_item, str_path)

    # 자막 추출
    if subtitles_enabled and plex_item:
        srt_files = extract_subtitles(str_path)
        if srt_files: upload_subtitles(plex_item, srt_files)

    if DEBUG: logging.debug(f"[DEBUG] Finished processing: {str_path}, success={success}")
    return success

# ==============================
# Watchdog
# ==============================
event_queue = Queue()
class WatchHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory: return
        if Path(event.src_path).suffix.lower() in VIDEO_EXTS:
            event_queue.put(event.src_path)

def watch_worker(stop_event):
    while not stop_event.is_set():
        try:
            file_path = event_queue.get(timeout=1)
            logging.info(f"[WATCH] Processing {file_path}")
            process_single_file(file_path)
            event_queue.task_done()
        except Empty:
            continue

# ==============================
# Initial scan
# ==============================
def scan_and_update_cache():
    video_files=[]
    for lib_id in config["plex_library_ids"]:
        try: section=plex.library.sectionByID(lib_id)
        except: continue
        for p in getattr(section,"locations",[]):
            for root,dirs,files in os.walk(p):
                for f in files:
                    if f.lower().endswith(VIDEO_EXTS):
                        full_path = os.path.abspath(os.path.join(root,f))
                        video_files.append(full_path)
                        if full_path not in cache:
                            plex_item=find_plex_item(full_path)
                            if plex_item: update_cache(full_path, plex_item.ratingKey)
                        nfo_path=Path(full_path).with_suffix(".nfo")
                        if nfo_path.exists() and nfo_path.stat().st_size>0:
                            plex_item=find_plex_item(full_path)
                            if plex_item: apply_nfo(plex_item,full_path)
    save_cache()
    return video_files

# ==============================
# Main
# ==============================
def main():
    logging.info("START")
    setup_ffmpeg()
    video_files = scan_and_update_cache()  # 항상 리스트 반환

    if DEBUG: logging.debug(f"[DEBUG] Total video files: {len(video_files)}")

    if threads > 1:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(process_single_file, f): f for f in video_files}
            for fut in as_completed(futures):
                _ = fut.result()
    else:
        for f in video_files:
            process_single_file(f)

    save_cache()
    logging.info("END")

    stop_event=threading.Event()
    if config.get("watch_folders",True):
        observer=Observer()
        for lib_id in config["plex_library_ids"]:
            try: section=plex.library.sectionByID(lib_id)
            except: continue
            for loc in getattr(section,"locations",[]):
                observer.schedule(WatchHandler(),loc,recursive=True)
        observer.start()
        watch_thread=threading.Thread(target=watch_worker,args=(stop_event,),daemon=True)
        watch_thread.start()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            stop_event.set()
            observer.stop()
            observer.join()

if __name__=="__main__":
    logging.info("START")
    main()
    logging.info("END")
