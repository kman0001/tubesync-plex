import os
import threading
from pathlib import Path
import lxml.etree as ET
from tubesync_plex.subtitles import extract_subtitles, upload_subtitles

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
processed_files = set()
cache_lock = threading.Lock()

def process_file(file_path, plex, config, ignore_processed=False):
    abs_path = Path(file_path).resolve()
    if not ignore_processed and abs_path in processed_files: return False
    if not abs_path.suffix.lower() in VIDEO_EXTS: return False

    key = config.get("cache", {}).get(str(abs_path))
    plex_item = None
    if key:
        try: plex_item = plex.fetchItem(key)
        except Exception: plex_item = None
    if not plex_item:
        plex_item = find_plex_item(abs_path, plex, config)
        if plex_item: config["cache"][str(abs_path)] = plex_item.key

    nfo_path = abs_path.with_suffix(".nfo")
    success = False
    if nfo_path.exists() and nfo_path.stat().st_size > 0 and plex_item:
        try:
            tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
            root = tree.getroot()
            title = root.findtext("title","")
            plot = root.findtext("plot","")
            aired = root.findtext("aired","")
            if not config.get("silent", False):
                print(f"[INFO] Applying NFO: {abs_path} -> {title}")
            plex_item.editTitle(title, locked=True)
            plex_item.editSortTitle(aired, locked=True)
            plex_item.editSummary(plot, locked=True)
            if config.get("subtitles", False):
                srt_files = extract_subtitles(str(abs_path))
                if srt_files:
                    from threading import Semaphore
                    sema = Semaphore(config.get("max_concurrent_requests",2))
                    upload_subtitles(plex_item, srt_files, sema, config.get("request_delay",0.1))
            try: nfo_path.unlink()
            except Exception: pass
            success = True
        except Exception:
            pass
    processed_files.add(abs_path)
    return success

def scan_and_update_cache(plex, config):
    import os
    all_files = []
    for lib_id in config["plex_library_ids"]:
        try: section = plex.library.sectionByID(lib_id)
        except Exception: continue
        for p in getattr(section, "locations", []):
            for root, dirs, files in os.walk(p):
                for f in files: all_files.append(os.path.join(root,f))

    current_files = set()
    for f in all_files:
        abs_path = os.path.abspath(f)
        if not f.lower().endswith(VIDEO_EXTS): continue
        current_files.add(abs_path)
        if abs_path not in config["cache"]:
            plex_item = find_plex_item(abs_path, plex, config)
            if plex_item:
                config["cache"][abs_path] = plex_item.key

    removed = set(config["cache"].keys()) - current_files
    for f in removed:
        config["cache"].pop(f,None)

def save_cache():
    pass  # CLI에서 json 파일 저장 처리
def find_plex_item(abs_path, plex, config):
    for lib_id in config["plex_library_ids"]:
        try: section = plex.library.sectionByID(lib_id)
        except Exception: continue
        for item in section.all():
            for part in item.iterParts():
                if os.path.abspath(part.file) == abs_path:
                    return item
    return None
