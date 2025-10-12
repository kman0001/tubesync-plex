import threading, time, queue, logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from core.nfo_processor import process_nfo
from core.cache import cache, update_cache, remove_from_cache, save_cache
from core.plex_helper import find_plex_item
from core.settings import VIDEO_EXTS, WATCH_DEBOUNCE_DELAY, DELAY_AFTER_NEW_FILE, CACHE_REPAIR_INTERVAL, schedule_cache_repair

processed_files = set()
processed_files_lock = threading.Lock()
logged_failures = set()
logged_successes = set()

class MediaFileHandler(FileSystemEventHandler):
    MAX_NFO_RETRY = 5
    MAX_RETRY_DELAY = 600

    def __init__(self, nfo_wait=30, video_wait=5, debounce_delay=1.0):
        self.nfo_wait = nfo_wait
        self.video_wait = video_wait
        self.debounce_delay = debounce_delay
        self.retry_queue = {}
        self.last_event_time = {}

    def _debounce(self, path):
        now = time.time()
        last_time = self.last_event_time.get(path, 0)
        if now - last_time < self.debounce_delay:
            return False
        self.last_event_time[path] = now
        return True

    def _enqueue_retry(self, path, delay, retry_count=0, is_nfo=False):
        self.retry_queue[path] = (time.time() + delay, delay, retry_count, is_nfo)
        logging.debug(f"[WATCHDOG] Enqueued for retry ({'NFO' if is_nfo else 'VIDEO'}): {path} (delay={delay}s, retry={retry_count})")

    def process_retry_queue(self):
        global cache
        now = time.time()
        ready = [p for p, (t, _, _, _) in self.retry_queue.items() if t <= now]

        for path in ready:
            next_time, delay, retry_count, is_nfo = self.retry_queue.pop(path)
            p = Path(path)
