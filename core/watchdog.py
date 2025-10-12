import time
import logging
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from core.cache import cache, save_cache, remove_from_cache
from core.nfo import process_nfo
from core.processing import process_file

WATCH_DEBOUNCE_DELAY = 1.0

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
        logging.debug(f"[WATCHDOG] Enqueued retry: {path}")

    def process_retry_queue(self):
        now = time.time()
        ready = [p for p, (t, _, _, _) in self.retry_queue.items() if t <= now]
        for path in ready:
            next_time, delay, retry_count, is_nfo = self.retry_queue.pop(path)
            p = Path(path)
            if not p.exists():
                remove_from_cache(path)
                continue
            success = False
            if is_nfo:
                logging.info(f"[WATCHDOG] Processing NFO: {path}")
                success = process_nfo(str(p.resolve()))
            elif p.suffix.lower() in (".mkv",".mp4",".avi",".mov",".wmv",".flv",".m4v"):
                logging.info(f"[WATCHDOG] Processing video: {path}")
                success = process_file(str(p.resolve()))
            if not success:
                if retry_count + 1 < self.MAX_NFO_RETRY:
                    new_delay = min(delay*2, self.MAX_RETRY_DELAY)
                    self._enqueue_retry(path, new_delay, retry_count+1, is_nfo)
                    logging.warning(f"[WATCHDOG] Retry scheduled for {path} in {new_delay}s")

    def on_created(self, event):
        if not self._debounce(event.src_path):
            return
        ext = Path(event.src_path).suffix.lower()
        if ext in (".mkv",".mp4",".avi",".mov",".wmv",".flv",".m4v"):
            self._enqueue_retry(event.src_path, self.video_wait)
        elif ext == ".nfo":
            self._enqueue_retry(event.src_path, self.nfo_wait)

def start_watchdog(base_dirs):
    observer = Observer()
    handler = MediaFileHandler(debounce_delay=WATCH_DEBOUNCE_DELAY)
    for d in base_dirs:
        observer.schedule(handler, d, recursive=True)
    observer.start()
    logging.info("[WATCHDOG] Started observer")

    try:
        while True:
            handler.process_retry_queue()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("[WATCHDOG] Stopping observer")
        observer.stop()
        observer.join()
