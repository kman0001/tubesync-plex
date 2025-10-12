import json
import threading
from pathlib import Path
import logging

cache_lock = threading.Lock()
cache_modified = False
cache = {}

def init_cache(cache_file: Path):
    global cache
    if cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as f:
            cache = json.load(f)
    else:
        cache = {}
    return cache

def save_cache(cache_file: Path):
    global cache_modified
    with cache_lock:
        if cache_modified:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with cache_file.open("w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            logging.info(f"[CACHE] Saved to {cache_file}, {len(cache)} entries")
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
        logging.debug(f"[CACHE] update_cache: {path} => {current}")

def remove_from_cache(video_path):
    global cache_modified
    path = str(video_path)
    with cache_lock:
        if path in cache:
            cache.pop(path)
            cache_modified = True
            logging.debug(f"[CACHE] remove_from_cache: {path}")
