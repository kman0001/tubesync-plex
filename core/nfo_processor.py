from pathlib import Path
import hashlib
import logging
import lxml.etree as ET
from core.cache import update_cache
from core.plex_helper import find_plex_item, plex

deleted_nfo_set = set()
nfo_lock = threading.Lock()

def compute_nfo_hash(nfo_path):
    try:
        with open(nfo_path, "rb") as f:
            data = f.read()
        h = hashlib.md5(data).hexdigest()
        logging.debug(f"[NFO] compute_nfo_hash: {nfo_path} -> {h}")
        return h
    except Exception as e:
        logging.error(f"[NFO] Failed to compute NFO hash: {nfo_path} - {e}")
        return None

def safe_edit(ep, title=None, summary=None, aired=None):
    try:
        kwargs = {}
        if title is not None:
            kwargs['title.value'] = title
            kwargs['title.locked'] = 1
        if summary is not None:
            kwargs['summary.value'] = summary
            kwargs['summary.locked'] = 1
        if aired is not None:
            kwargs['originallyAvailableAt.value'] = aired
            kwargs['originallyAvailableAt.locked'] = 1

        if kwargs:
            ep.edit(**kwargs)
            ep.reload()
        return True
    except Exception as e:
        logging.error(f"[SAFE_EDIT] Failed to edit item: {e}", exc_info=True)
        return False

def apply_nfo(ep, file_path):
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False

    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title", "").strip() or None
        plot = root.findtext("plot", "").strip() or None
        aired = root.findtext("aired", "").strip() or None
        title_sort = root.findtext("titleSort", "").strip() or title

        if not safe_edit(ep, title=title, summary=plot, aired=aired):
            return False

        if title_sort:
            try:
                ep.editSortTitle(title_sort, locked=True)
            except Exception:
                ep.edit(**{"titleSort.value": title_sort, "titleSort.locked": 1})
            ep.reload()

        return True
    except Exception as e:
        logging.error(f"[!] Error applying NFO {nfo_path}: {e}", exc_info=True)
        return False

def process_nfo(file_path, ALWAYS_APPLY_NFO=True, DELETE_NFO_AFTER_APPLY=True):
    p = Path(file_path)
    if p.suffix.lower() == ".nfo":
        nfo_path = p
        video_path = p.with_suffix("")
        if not video_path.exists():
            for ext in [".mp4",".mkv",".avi",".mov"]:
                candidate = p.with_suffix(ext)
                if candidate.exists():
                    video_path = candidate
                    break
    else:
        video_path = p
        nfo_path = p.with_suffix(".nfo")

    if not nfo_path.exists() or nfo_path.stat().st_size == 0:
        return False

    str_video_path = str(video_path.resolve())
    nfo_hash = compute_nfo_hash(nfo_path)
    if nfo_hash is None:
        return False

    cached = cache.get(str_video_path, {})
    cached_hash = cached.get("nfo_hash")

    if cached_hash == nfo_hash and not ALWAYS_APPLY_NFO:
        logging.info(f"[CACHE] Skipping already applied NFO: {str_video_path}")
        if DELETE_NFO_AFTER_APPLY:
            with nfo_lock:
                if nfo_path not in deleted_nfo_set:
                    try:
                        nfo_path.unlink()
                    except Exception as e:
                        logging.warning(f"[WARN] Failed to delete NFO {nfo_path}: {e}")
                    deleted_nfo_set.add(nfo_path)
        return True

    plex_item = None
    ratingKey = cached.get("ratingKey")
    if cached_hash != nfo_hash or ALWAYS_APPLY_NFO:
        if ratingKey:
            try:
                plex_item = plex.fetchItem(ratingKey)
            except Exception:
                plex_item = None

        if not plex_item:
            plex_item = find_plex_item(str_video_path)
            if plex_i_
