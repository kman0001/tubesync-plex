import json
import threading
from pathlib import Path
from core.config import CACHE_FILE
import logging

cache = {}
cache_modified = False
cache_lock = threading.Lock()

if CACHE_FILE.exists():
    with CACHE_FILE.open("r", encoding="utf-8") as f:
        cache = json.load(f)

def save_cache():
    global cache_modified
    with cache_lock:
        if cache_modified:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            logging.info(f"[CACHE] Saved to {CACHE_FILE}, {len(cache)} entries")
            cache_modified = False

def update_cache(video_path, ratingKey=None, nfo_hash=None):
    global cache_modified
    path = str(video_path)
    with cache_lock:
        current = cache.get(path, {})
        if ratingKey is not None:
            current["ratingKey"] = ratingKey
        if nfo_hash is not None:
            current["nfo_hash"] = nfo_hash
        cache[path] = current
        cache_modified = True

def remove_from_cache(video_path):
    global cache_modified
    path = str(video_path)
    with cache_lock:
        if path in cache:
            cache.pop(path, None)
            cache_modified = True
