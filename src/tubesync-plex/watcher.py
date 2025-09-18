import os, threading, time
from watchdog.events import FileSystemEventHandler

class VideoEventHandler(FileSystemEventHandler):
    def __init__(self, plex, config):
        self.plex = plex
        self.config = config
        self.nfo_queue = set()
        self.video_queue = set()
        self.lock = threading.Lock()
        self.nfo_timer = None
        self.video_timer = None

    def on_any_event(self, event):
        if event.is_directory:
            return
        path = os.path.abspath(event.src_path)
        ext = os.path.splitext(path)[1].lower()
        with self.lock:
            if event.event_type == "deleted":
                self.config["cache"].pop(path, None)
            elif event.event_type == "created":
                if ext in [".mp4",".mkv",".avi"]:
                    self.video_queue.add(path)
                    if not self.video_timer:
                        self.video_timer = threading.Timer(2, self.process_video_queue)
                        self.video_timer.start()
                elif ext == ".nfo":
                    self.nfo_queue.add(path)
                    if not self.nfo_timer:
                        self.nfo_timer = threading.Timer(5, self.process_nfo_queue)
                        self.nfo_timer.start()

    def process_video_queue(self):
        with self.lock:
            queue = list(self.video_queue)
            self.video_queue.clear()
            self.video_timer = None
        from metadata import process_file
        for f in queue:
            process_file(f, self.plex, self.config)

    def process_nfo_queue(self):
        with self.lock:
            queue = list(self.nfo_queue)
            self.nfo_queue.clear()
            self.nfo_timer = None
        from metadata import process_file
        for f in queue:
            process_file(f, self.plex, self.config)
