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

            if not p.exists():
                logging.info(f"[WATCHDOG] Path no longer exists, removing from cache: {path}")
                remove_from_cache(path)
                continue

            ext = p.suffix.lower()
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

            success = False
            if ext in VIDEO_EXTS:
                logging.info(f"[WATCHDOG] Processing video: {path}")
                from core.video_processor import process_file  # lazy import to avoid circular
                success = process_file(str(p.resolve()))
            elif ext == ".nfo":
                logging.info(f"[WATCHDOG] Processing NFO: {path}")
                success = process_nfo(str(p.resolve()))

            if not success:
                if is_nfo and retry_count + 1 >= self.MAX_NFO_RETRY:
                    logging.warning(f"[WATCHDOG] Max retries reached for NFO: {path}")
                    continue
                new_delay = min(delay * 2, self.MAX_RETRY_DELAY)
                self._enqueue_retry(path, new_delay, retry_count + 1, is_nfo)
                logging.warning(f"[WATCHDOG] Retry scheduled for {path} in {new_delay}s (retry #{retry_count + 1})")

        save_cache()

    def on_created(self, event):
        if not self._debounce(event.src_path):
            return
        path = str(Path(event.src_path).resolve())
        ext = Path(path).suffix.lower()
        if ext in VIDEO_EXTS:
            self._enqueue_retry(path, self.video_wait, is_nfo=False)
        elif ext == ".nfo":
            self._enqueue_retry(path, self.nfo_wait, is_nfo=True)

    def on_deleted(self, event):
        path = str(Path(event.src_path).resolve())
        remove_from_cache(path)

    def on_moved(self, event):
        src = str(Path(event.src_path).resolve())
        dest = str(Path(event.dest_path).resolve()) if getattr(event, "dest_path", None) else None
        remove_from_cache(src)
        if dest and not event.is_directory:
            self.on_created(event)

def start_watchdog(base_dirs):
    observer = Observer()
    handler = MediaFileHandler(debounce_delay=WATCH_DEBOUNCE_DELAY)

    for d in base_dirs:
        observer.schedule(handler, d, recursive=True)
    observer.start()
    logging.info("[WATCHDOG] Started observer")
    schedule_cache_repair(CACHE_REPAIR_INTERVAL)

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
        observer.join()
