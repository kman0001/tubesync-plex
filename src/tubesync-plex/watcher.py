# src/tubesync_plex/watcher.py
import os
import threading
import time
from pathlib import Path
from watchdog.events import FileSystemEventHandler
import logging

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

class VideoEventHandler(FileSystemEventHandler):
    """Handle create/delete events for video and NFO files with debounce.
       This class requires:
         - plex: PlexServer instance
         - config: dict
         - cache_mgr: CacheManager instance
         - process_file_func: callable(file_path, plex, config, cache_mgr, api_semaphore, request_delay, processed_files, detail)
         - api_semaphore, request_delay, processed_files, detail
    """
    def __init__(self, plex, config, cache_mgr, process_file_func, api_semaphore, request_delay, processed_files:set, detail=False):
        super().__init__()
        self.plex = plex
        self.config = config
        self.cache_mgr = cache_mgr
        self.process_file = process_file_func
        self.api_semaphore = api_semaphore
        self.request_delay = request_delay
        self.processed_files = processed_files
        self.detail = detail

        self.nfo_queue = set()
        self.video_queue = set()
        self.lock = threading.Lock()
        self.nfo_timer = None
        self.video_timer = None
        self.retry_queue = {}  # {path: (timestamp, count)}

    def on_any_event(self, event):
        if event.is_directory:
            return
        path = os.path.abspath(event.src_path)
        ext = os.path.splitext(path)[1].lower()
        with self.lock:
            if event.event_type == "deleted" and ext in VIDEO_EXTS:
                self.cache_mgr.remove(path)
                self.cache_mgr.save()
            elif event.event_type == "created" and ext in VIDEO_EXTS:
                if not self.cache_mgr.contains(path):
                    plex_item = None
                    # try to find plex_item quickly
                    try:
                        for lib_id in self.config.get("plex_library_ids", []):
                            try:
                                section = self.plex.library.sectionByID(lib_id)
                            except Exception:
                                continue
                            found = None
                            for item in section.all():
                                try:
                                    for part in item.iterParts():
                                        if os.path.abspath(part.file) == path:
                                            found = item
                                            break
                                    if found:
                                        plex_item = found
                                        break
                                except Exception:
                                    continue
                            if plex_item:
                                break
                    except Exception:
                        plex_item = None

                    if plex_item:
                        self.cache_mgr.update(path, plex_item.key)
                        self.cache_mgr.save()
                self.schedule_video(path)
            elif ext == ".nfo":
                self.schedule_nfo(path)

    def schedule_nfo(self, path):
        self.nfo_queue.add(path)
        if not self.nfo_timer:
            delay = self.config.get("watch_debounce_delay", 10)
            self.nfo_timer = threading.Timer(delay, self.process_nfo_queue)
            self.nfo_timer.start()

    def schedule_video(self, path):
        self.video_queue.add(path)
        if not self.video_timer:
            delay = self.config.get("watch_debounce_delay", 2)
            self.video_timer = threading.Timer(delay, self.process_video_queue)
            self.video_timer.start()

    def process_nfo_queue(self):
        with self.lock:
            queue = list(self.nfo_queue)
            self.nfo_queue.clear()
            self.nfo_timer = None
        for nfo_path in queue:
            # find video counterpart
            video_path = self._find_video(nfo_path)
            if video_path:
                try:
                    self.process_file(video_path, self.plex, self.config, self.cache_mgr, self.api_semaphore, self.request_delay, self.processed_files, detail=self.detail)
                except Exception as e:
                    logging.error(f"Error processing file from nfo event {video_path}: {e}")
        self._process_retry()

    def process_video_queue(self):
        with self.lock:
            queue = list(self.video_queue)
            self.video_queue.clear()
            self.video_timer = None
        for video_path in queue:
            try:
                self.process_file(video_path, self.plex, self.config, self.cache_mgr, self.api_semaphore, self.request_delay, self.processed_files, detail=self.detail)
            except Exception as e:
                logging.error(f"Error processing video event {video_path}: {e}")
        self.cache_mgr.save()

    def _find_video(self, nfo_path):
        for ext in VIDEO_EXTS:
            candidate = str(Path(nfo_path).with_suffix(ext))
            if os.path.exists(candidate):
                return candidate
        return None

    def _process_retry(self):
        now = time.time()
        for path, (retry_time, count) in list(self.retry_queue.items()):
            if now >= retry_time:
                if self.process_file(path, self.plex, self.config, self.cache_mgr, self.api_semaphore, self.request_delay, self.processed_files, detail=self.detail):
                    del self.retry_queue[path]
                elif count < 3:
                    self.retry_queue[path] = (now + 5, count + 1)
                else:
                    logging.warning(f"[WARN] NFO failed 3x: {path}")
                    del self.retry_queue[path]
