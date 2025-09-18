import os, json
from pathlib import Path
from lxml import etree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from subtitles import extract_subtitles, upload_subtitles
from utils import VIDEO_EXTS

def scan_and_update_cache(plex, config):
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

    for f in all_files:
        abs_path = os.path.abspath(f)
        if not f.lower().endswith(VIDEO_EXTS):
            continue
        if abs_path not in config["cache"]:
            for lib_id in config["plex_library_ids"]:
                try:
                    section = plex.library.sectionByID(lib_id)
                except Exception:
                    continue
                for item in section.all():
                    for part in item.iterParts():
                        if os.path.abspath(part.file) == abs_path:
                            config["cache"][abs_path] = item.key

def save_cache(config, cache_file):
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(config["cache"], f, indent=2, ensure_ascii=False)

def process_file(file_path, plex, config):
    abs_path = Path(file_path).resolve()
    cache = config["cache"]
    plex_item = None
    key = cache.get(str(abs_path))
    if key:
        try:
            plex_item = plex.fetchItem(key)
        except:
            plex_item = None
    if not plex_item:
        # find Plex item
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except:
                continue
            for item in section.all():
                for part in item.iterParts():
                    if os.path.abspath(part.file) == str(abs_path):
                        plex_item = item
                        cache[str(abs_path)] = item.key

    if not plex_item:
        return False

    nfo_path = abs_path.with_suffix(".nfo")
    if nfo_path.exists() and nfo_path.stat().st_size > 0:
        try:
            tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
            root = tree.getroot()
            title = root.findtext("title","")
            plot = root.findtext("plot","")
            aired = root.findtext("aired","")
            plex_item.editTitle(title, locked=True)
            plex_item.editSortTitle(aired, locked=True)
            plex_item.editSummary(plot, locked=True)

            if config.get("subtitles", False):
                srt_files = extract_subtitles(str(abs_path))
                upload_subtitles(plex_item, srt_files)

            nfo_path.unlink()
            return True
        except:
            return False
    return False
