import os, threading
from pathlib import Path
import lxml.etree as ET
from .subtitles import extract_subtitles, upload_subtitles
from .utils import safe_print

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
processed_files = set()
cache_lock = threading.Lock()
cache_modified = False

def process_file(file_path, plex, config, ignore_processed=False, cache=None, semaphore=None):
    abs_path = Path(file_path).resolve()
    if not ignore_processed and abs_path in processed_files:
        return False
    if not abs_path.suffix.lower() in VIDEO_EXTS:
        return False

    plex_item = None
    key = cache.get(str(abs_path)) if cache else None
    if key:
        try:
            plex_item = plex.fetchItem(key)
        except Exception:
            plex_item = None
    if not plex_item:
        # 검색
        plex_item = find_plex_item(abs_path, plex, config)
        if plex_item and cache is not None:
            cache[str(abs_path)] = plex_item.key

    if plex_item:
        nfo_path = abs_path.with_suffix(".nfo")
        if nfo_path.exists() and nfo_path.stat().st_size > 0:
            try:
                tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
                root = tree.getroot()
                title = root.findtext("title","")
                plot = root.findtext("plot","")
                aired = root.findtext("aired","")
                if not config.get("silent", False):
                    safe_print(f"[INFO] Applying NFO: {abs_path} -> {title}")
                plex_item.editTitle(title, locked=True)
                plex_item.editSortTitle(aired, locked=True)
                plex_item.editSummary(plot, locked=True)
                if config.get("subtitles", False):
                    srt_files = extract_subtitles(str(abs_path))
                    if srt_files and semaphore:
                        upload_subtitles(plex_item, srt_files, semaphore, config.get("request_delay",0.1), config.get("detail",False))
                try:
                    nfo_path.unlink()
                except Exception:
                    pass
                processed_files.add(abs_path)
                return True
            except Exception as e:
                safe_print(f"[ERROR] NFO processing failed: {nfo_path} - {e}")
    processed_files.add(abs_path)
    return False

def find_plex_item(abs_path, plex, config):
    for lib_id in config["plex_library_ids"]:
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue
        for item in section.all():
            for part in getattr(item, "iterParts", lambda: [])():
                if os.path.abspath(part.file) == str(abs_path):
                    return item
    return None

def scan_and_update_cache(plex, config, cache=None):
    if cache is None:
        cache = {}
    existing_files = set(cache.keys())
    all_files = []
    for lib_id in config["plex_library_ids"]:
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
        if abs_path not in cache:
            plex_item = find_plex_item(abs_path, plex, config)
            if plex_item:
                cache[abs_path] = plex_item.key

    # 삭제된 파일 제거
    removed = existing_files - current_files
    for f in removed:
        cache.pop(f, None)

def save_cache(cache_file, cache):
    with cache_lock:
        with open(cache_file, "w", encoding="utf-8") as f:
            import json
            json.dump(cache, f, indent=2, ensure_ascii=False)
