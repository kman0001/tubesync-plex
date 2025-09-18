# src/tubesync_plex/utils.py
from pathlib import Path
import json
import threading
import logging
import os

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

class CacheManager:
    """Encapsulate cache state + persistence."""
    def __init__(self, cache_file: Path):
        self.cache_file = Path(cache_file)
        self.lock = threading.Lock()
        self._cache = {}
        self.modified = False
        self.load()

    def load(self):
        if self.cache_file.exists():
            try:
                with self.cache_file.open("r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception as e:
                logging.warning(f"Failed to load cache {self.cache_file}: {e}")
                self._cache = {}
        else:
            self._cache = {}

    def save(self):
        with self.lock:
            if not self.modified:
                return
            try:
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                with self.cache_file.open("w", encoding="utf-8") as f:
                    json.dump(self._cache, f, indent=2, ensure_ascii=False)
                logging.debug(f"Saved cache to {self.cache_file}, items: {len(self._cache)}")
                self.modified = False
            except Exception as e:
                logging.error(f"Failed to save cache: {e}")

    def get(self, path):
        return self._cache.get(path)

    def update(self, path, key):
        with self.lock:
            if self._cache.get(path) != key:
                self._cache[path] = key
                self.modified = True

    def remove(self, path):
        with self.lock:
            if path in self._cache:
                del self._cache[path]
                self.modified = True

    def keys(self):
        return list(self._cache.keys())

    def items(self):
        return list(self._cache.items())

    def contains(self, path):
        return path in self._cache

def scan_and_update_cache(plex, config, cache_mgr):
    """
    Walk filesystem locations reported by Plex libraries in config["plex_library_ids"]
    and update cache entries by attempting to find Plex items for files not in cache.
    """
    existing_files = set(cache_mgr.keys())
    all_files = []

    for lib_id in config.get("plex_library_ids", []):
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue
        for p in getattr(section, "locations", []):
            for root, dirs, files in os.walk(p):
                for f in files:
                    all_files.append(os.path.join(root, f))

    current_files = set()
    for f in all_files:
        abs_path = os.path.abspath(f)
        if not f.lower().endswith(VIDEO_EXTS):
            continue
        current_files.add(abs_path)
        if not cache_mgr.contains(abs_path):
            # attempt to locate Plex item
            plex_item = None
            try:
                # iterate section items could be heavy; try find by parts
                for lib_id in config.get("plex_library_ids", []):
                    try:
                        section = plex.library.sectionByID(lib_id)
                    except Exception:
                        continue
                    for item in section.all():
                        for part in item.iterParts():
                            if os.path.abspath(part.file) == abs_path:
                                plex_item = item
                                break
                        if plex_item:
                            break
                    if plex_item:
                        break
            except Exception as e:
                logging.debug(f"scan: error searching plex for {abs_path}: {e}")
                plex_item = None

            if plex_item:
                cache_mgr.update(abs_path, plex_item.key)

    # Remove deleted files from cache
    removed = existing_files - current_files
    for f in removed:
        cache_mgr.remove(f)
