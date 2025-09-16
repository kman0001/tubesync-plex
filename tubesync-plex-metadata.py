#!/usr/bin/env python3
import os, sys, json, time, threading, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from plexapi.server import PlexServer
import lxml.etree as ET
import argparse
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# -----------------------------
# Argument parsing
# -----------------------------
parser = argparse.ArgumentParser(description="TubeSync Plex Metadata Sync")
parser.add_argument("--disable-watchdog", action="store_true", help="Disable folder watching")
parser.add_argument("--config", type=str, default=None, help="Path to config.json")
args = parser.parse_args()
DISABLE_WATCHDOG = args.disable_watchdog

# -----------------------------
# Directories
# -----------------------------
BASE_DIR = os.environ.get("BASE_DIR", "/app")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)
CONFIG_FILE = args.config or os.path.join(CONFIG_DIR, "config.json")
CACHE_FILE = os.path.join(os.path.dirname(CONFIG_FILE), "tubesync_cache.json")

# -----------------------------
# Default config
# -----------------------------
default_config = {
    "_comment": {
        "plex_base_url": "Plex server URL, e.g., http://localhost:32400",
        "plex_token": "Plex server token",
        "plex_library_ids": "List of Plex library IDs to sync, e.g., [10,21,35]",
        "silent": "true/false",
        "detail": "true/false",
        "subtitles": "true/false",
        "threads": "number of threads, e.g., 8",
        "max_concurrent_requests": "concurrent Plex API requests, e.g., 4",
        "request_delay": "delay between API requests (seconds), e.g., 0.1",
        "watch_folders": "enable folder watching, true/false",
        "watch_debounce_delay": "debounce time for folder watching (seconds), e.g., 2"
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

# -----------------------------
# Load/Create config
# -----------------------------
if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    sys.exit(0)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

if DISABLE_WATCHDOG:
    config["watch_folders"] = False

# -----------------------------
# Plex connection
# -----------------------------
try:
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
except Exception as e:
    print(f"[ERROR] Failed to connect to Plex: {e}")
    sys.exit(1)

# -----------------------------
# Globals
# -----------------------------
VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
api_semaphore = threading.Semaphore(config.get("max_concurrent_requests",2))
request_delay = config.get("request_delay",0.1)
threads = config.get("threads",4)
detail = config.get("detail",False)
subtitles_enabled = config.get("subtitles",False)
processed_files = set()
watch_debounce_delay = config.get("watch_debounce_delay",2)

# -----------------------------
# Cache
# -----------------------------
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE,"r",encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE,"w",encoding="utf-8") as f:
        json.dump(cache,f,indent=2,ensure_ascii=False)
    if detail: print(f"[CACHE] Created empty cache at {CACHE_FILE}")

def save_cache():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE,"w",encoding="utf-8") as f:
            json.dump(cache,f,indent=2,ensure_ascii=False)
        if detail: print(f"[CACHE] Saved cache to {CACHE_FILE}, total items: {len(cache)}")
    except Exception as e:
        print(f"[ERROR] Failed to save cache: {e}")

# -----------------------------
# Plex helpers
# -----------------------------
def find_plex_item(abs_path):
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except:
            continue
        section_type = getattr(section,"TYPE","").lower()
        if section_type=="show":
            results = section.search(libtype="episode")
        elif section_type in ("movie","video"):
            results = section.search(libtype="movie")
        else:
            continue
        for item in results:
            for part in item.iterParts():
                if os.path.abspath(part.file)==abs_path:
                    return item
    return None

def scan_and_update_cache():
    """Scan library, add missing meta IDs, remove deleted files."""
    global cache
    existing_files = set(cache.keys())
    all_files = []

    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except:
            continue
        paths = getattr(section,"locations",[])
        for p in paths:
            for root, dirs, files in os.walk(p):
                for f in files:
                    all_files.append(os.path.join(root,f))

    current_files = set()
    for f in all_files:
        abs_path = os.path.abspath(f)
        if not f.lower().endswith(VIDEO_EXTS):
            continue
        current_files.add(abs_path)
        # 캐시에 메타ID가 없으면 Plex에서 찾기
        if abs_path not in cache or cache.get(abs_path) is None:
            plex_item = find_plex_item(abs_path)
            if plex_item:
                cache[abs_path] = plex_item.key

    # 삭제된 파일은 캐시에서 제거
    removed = existing_files - current_files
    for f in removed:
        cache.pop(f,None)

# -----------------------------
# Subtitles
# -----------------------------
LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr","spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}
def map_lang(code): return LANG_MAP.get(code.lower(),"und")

def extract_subtitles(video_path):
    base,_ = os.path.splitext(video_path)
    srt_files=[]
    ffprobe_cmd = ["ffprobe","-v","error","-select_streams","s",
                   "-show_entries","stream=index:stream_tags=language,codec_name",
                   "-of","json",video_path]
    try:
        result = subprocess.run(ffprobe_cmd,capture_output=True,text=True)
        streams = json.loads(result.stdout).get("streams",[])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags",{}).get("language","und"))
            srt = f"{base}.{lang}.srt"
            if os.path.exists(srt): continue
            subprocess.run(["ffmpeg","-y","-i",video_path,f"-map","0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if os.path.exists(srt): srt_files.append((srt,lang))
    except Exception as e:
        print(f"[ERROR] ffprobe/ffmpeg failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep, srt_files):
    for srt, lang in srt_files:
        try:
            with api_semaphore:
                ep.uploadSubtitles(srt, language=lang)
                time.sleep(request_delay)
            if detail: print(f"[SUBTITLE] Uploaded: {srt}")
        except Exception as e:
            print(f"[ERROR] Subtitle upload failed: {srt} - {e}")

# -----------------------------
# Apply NFO
# -----------------------------
def apply_nfo(ep, file_path):
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size==0: return False
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title","")
        plot = root.findtext("plot","")
        aired = root.findtext("aired","")

        if detail:
            print(f"[-] Applying NFO: {file_path} -> {title}")

        ep.editTitle(title,locked=True)
        ep.editSortTitle(aired,locked=True)
        ep.editSummary(plot,locked=True)

        if subtitles_enabled:
            srt_files = extract_subtitles(file_path)
            if srt_files: upload_subtitles(ep,srt_files)

        try:
            nfo_path.unlink()
            if detail: print(f"[-] Deleted NFO: {nfo_path}")
        except Exception as e:
            print(f"[WARN] Failed to delete NFO file: {nfo_path} - {e}")

        return True
    except Exception as e:
        print(f"[!] Error processing {nfo_path}: {e}")
        return False

# -----------------------------
# Process single file
# -----------------------------
def process_file(file_path):
    abs_path = os.path.abspath(file_path)
    if not file_path.lower().endswith(VIDEO_EXTS):
        return False

    plex_item = None
    key = cache.get(abs_path)
    if key:
        try:
            plex_item = plex.fetchItem(key)
        except:
            plex_item = None

    if not plex_item:
        plex_item = find_plex_item(abs_path)
        if plex_item:
            cache[abs_path] = plex_item.key

    nfo_path = Path(file_path).with_suffix(".nfo")
    success = False
    # NFO가 있으면 항상 적용
    if nfo_path.exists() and nfo_path.stat().st_size > 0 and plex_item:
        success = apply_nfo(plex_item, abs_path)

    # 영상 처리용으로만 processed_files에 기록
    if abs_path not in processed_files:
        processed_files.add(abs_path)

    return success

# -----------------------------
# Process single file
# -----------------------------
def process_file(file_path, ignore_processed=False):
    abs_path = os.path.abspath(file_path)
    if not ignore_processed and abs_path in processed_files:
        return False
    if not file_path.lower().endswith(VIDEO_EXTS):
        return False

    plex_item = None
    key = cache.get(abs_path)
    if key:
        try:
            plex_item = plex.fetchItem(key)
        except:
            plex_item = None

    if not plex_item:
        plex_item = find_plex_item(abs_path)
        if plex_item:
            cache[abs_path] = plex_item.key

    nfo_path = Path(file_path).with_suffix(".nfo")
    success = False
    if nfo_path.exists() and nfo_path.stat().st_size > 0 and plex_item:
        success = apply_nfo(plex_item, abs_path)

    processed_files.add(abs_path)
    return success

# -----------------------------
# Watchdog
# -----------------------------
class VideoEventHandler(FileSystemEventHandler):
    def __init__(self):
        self.nfo_queue = set()
        self.video_queue = set()
        self.lock = threading.Lock()
        self.nfo_timer = None
        self.video_timer = None
        self.nfo_wait = 10   # NFO 마지막 이벤트 후 10초 대기
        self.video_wait = 2  # 영상 마지막 이벤트 후 2초 대기
        self.logged_nfo = set()
        self.logged_video = set()
        self.retry_queue = {}

    def on_any_event(self, event):
        if event.is_directory:
            return

        path = os.path.abspath(event.src_path)
        ext = os.path.splitext(path)[1].lower()

        with self.lock:
            # 영상 삭제
            if event.event_type == "deleted" and ext in VIDEO_EXTS:
                if path in cache:
                    cache.pop(path, None)
                    if detail:
                        print(f"[CACHE] Removed deleted video from cache: {path}")
                    save_cache()
                return

            # 영상 생성
            elif event.event_type == "created" and ext in VIDEO_EXTS:
                if path not in cache:
                    plex_item = find_plex_item(path)
                    if plex_item:
                        cache[path] = plex_item.key
                        save_cache()
                self.schedule_video_processing(path)

            # 영상 수정 이벤트는 무시
            elif event.event_type == "modified" and ext in VIDEO_EXTS:
                return

            # NFO 생성/수정
            if ext == ".nfo":
                self.schedule_nfo_processing(path)

    def schedule_nfo_processing(self, path):
        self.nfo_queue.add(path)
        if not self.nfo_timer:
            self.nfo_timer = threading.Timer(self.nfo_wait, self.process_nfo_queue)
            self.nfo_timer.start()
        if detail and path not in self.logged_nfo:
            print(f"[DEBUG] Scheduled NFO processing for {path}")
            self.logged_nfo.add(path)

    def schedule_video_processing(self, path):
        self.video_queue.add(path)
        if not self.video_timer:
            self.video_timer = threading.Timer(self.video_wait, self.process_video_queue)
            self.video_timer.start()
        if detail and path not in self.logged_video:
            print(f"[DEBUG] Scheduled video processing for {path}")
            self.logged_video.add(path)

    def process_nfo_queue(self):
        with self.lock:
            nfo_files = list(self.nfo_queue)
            self.nfo_queue.clear()
            self.nfo_timer = None
            self.logged_nfo.clear()

        for nfo_path in nfo_files:
            video_path = self._find_corresponding_video(nfo_path)
            if video_path:
                # 캐시 업데이트
                if video_path not in cache or cache.get(video_path) is None:
                    plex_item = find_plex_item(video_path)
                    if plex_item:
                        cache[video_path] = plex_item.key
                # NFO 적용 (watchdog 이벤트는 항상 시도)
                success = process_file(video_path, ignore_processed=True)
                if not success:
                    self.retry_queue[video_path] = time.time() + 5  # 5초 후 재시도
        save_cache()
        self._process_retry_queue()

    def process_video_queue(self):
        with self.lock:
            video_files = list(self.video_queue)
            self.video_queue.clear()
            self.video_timer = None
            self.logged_video.clear()

        for video_path in video_files:
            if video_path not in cache or cache.get(video_path) is None:
                plex_item = find_plex_item(video_path)
                if plex_item:
                    cache[video_path] = plex_item.key
            process_file(video_path, ignore_processed=True)
        save_cache()

    def _find_corresponding_video(self, nfo_path):
        video_path = str(Path(nfo_path).with_suffix(".mkv"))
        if os.path.exists(video_path):
            return video_path
        for ext in VIDEO_EXTS:
            candidate = str(Path(nfo_path).with_suffix(ext))
            if os.path.exists(candidate):
                return candidate
        return None

    def _process_retry_queue(self):
        now = time.time()
        for video_path, retry_time in list(self.retry_queue.items()):
            if now >= retry_time:
                success = process_file(video_path, ignore_processed=True)
                if success:
                    del self.retry_queue[video_path]
                else:
                    self.retry_queue[video_path] = now + 5

# -----------------------------
# Main
# -----------------------------
def main():
    # 1. Scan library and update cache
    scan_and_update_cache()
    save_cache()

    # 2. Apply NFO to files
    total = 0
    all_files = list(cache.keys())
    with ThreadPoolExecutor(max_workers=threads) as ex:
        futures = [ex.submit(process_file, f) for f in all_files]
        for fut in as_completed(futures):
            if fut.result(): total += 1
    if not config.get("silent", False):
        print(f"[INFO] Total items updated: {total}")
    save_cache()

    # 3. Watchdog
    if config.get("watch_folders", False) and not DISABLE_WATCHDOG:
        observer = Observer()
        event_handler = VideoEventHandler()  # ← 단일 인스턴스 생성

        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except:
                continue
            for p in getattr(section, "locations", []):
                observer.schedule(event_handler, p, recursive=True)

        observer.start()
        print("[INFO] Watchdog started. Monitoring file changes...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__=="__main__":
    main()
