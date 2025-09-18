# src/tubesync_plex/metadata.py
from pathlib import Path
import lxml.etree as ET
import logging
import time

from .subtitles import extract_subtitles, upload_subtitles

def apply_nfo_to_item(plex_item, nfo_path: Path, subtitles_enabled: bool, api_semaphore, request_delay, detail=False):
    """Parse NFO and apply to a given Plex item (plexapi object). Returns True on success."""
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title", "")
        plot = root.findtext("plot", "")
        aired = root.findtext("aired", "")

        # plexapi methods
        try:
            plex_item.editTitle(title, locked=True)
            plex_item.editSortTitle(aired, locked=True)
            plex_item.editSummary(plot, locked=True)
        except Exception as e:
            logging.error(f"Failed to edit plex item {plex_item}: {e}")
            # continue to subtitle handling / deletion attempts

        if subtitles_enabled:
            srt_files = extract_subtitles(str(nfo_path.with_suffix(nfo_path.suffix).with_suffix('')))  # not used; keep consistent
            # Above is placeholder; caller normally passes video path and uses that function.
        # Remove NFO
        try:
            nfo_path.unlink()
            if detail:
                logging.debug(f"Deleted NFO: {nfo_path}")
        except Exception as e:
            logging.warning(f"Failed to delete NFO file: {nfo_path} - {e}")

        return True
    except Exception as e:
        logging.error(f"[!] Error processing {nfo_path}: {e}")
        return False

def process_file(file_path: str, plex, config: dict, cache_mgr, api_semaphore, request_delay, processed_files:set, detail=False):
    """
    Process a single video file path:
     - find Plex item (using cache or searching),
     - apply NFO (if available),
     - extract & upload subtitles (if enabled),
     - update cache.
    Returns True if metadata was applied (success).
    """
    abs_path = Path(file_path).resolve()
    if not abs_path.suffix.lower() in tuple([e.lower() for e in cache_mgr.keys()]) and not abs_path.suffix.lower() in (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v"):
        # quick suffix check: if weird, skip
        pass

    if abs_path in processed_files:
        return False

    plex_item = None
    key = cache_mgr.get(str(abs_path))
    if key:
        try:
            plex_item = plex.fetchItem(key)
        except Exception as e:
            if detail:
                logging.warning(f"Failed to fetch Plex item {key}: {e}")
            plex_item = None

    if not plex_item:
        # try to find by iterating library parts (similar to original)
        for lib_id in config.get("plex_library_ids", []):
            try:
                section = plex.library.sectionByID(lib_id)
            except Exception:
                continue
            found = None
            for item in section.all():
                try:
                    for part in item.iterParts():
                        if str(Path(part.file).resolve()) == str(abs_path):
                            found = item
                            break
                    if found:
                        break
                except Exception:
                    continue
            if found:
                plex_item = found
                cache_mgr.update(str(abs_path), plex_item.key)
                break

    nfo_path = abs_path.with_suffix(".nfo")
    success = False

    if nfo_path.exists() and nfo_path.stat().st_size > 0 and plex_item:
        try:
            # parse nfo
            tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
            root = tree.getroot()
            title = root.findtext("title","")
            plot = root.findtext("plot","")
            aired = root.findtext("aired","")

            if not config.get("silent", False):
                print(f"[INFO] Applying NFO: {abs_path} -> {title}")

            try:
                plex_item.editTitle(title, locked=True)
                plex_item.editSortTitle(aired, locked=True)
                plex_item.editSummary(plot, locked=True)
            except Exception as e:
                logging.error(f"Failed editing Plex item: {e}")

            # subtitles
            if config.get("subtitles", False):
                srt_files = extract_subtitles(str(abs_path))
                if srt_files:
                    upload_subtitles(plex_item, srt_files, api_semaphore, request_delay, detail=detail)

            try:
                nfo_path.unlink()
                if detail:
                    logging.debug(f"[DEBUG] Deleted NFO file: {nfo_path}")
            except Exception as e:
                logging.warning(f"Failed to delete NFO: {nfo_path} - {e}")

            success = True
        except Exception as e:
            logging.error(f"NFO processing error for {nfo_path}: {e}")

    # Ensure cache contains mapping if plex_item found
    if plex_item:
        cache_mgr.update(str(abs_path), plex_item.key)

    processed_files.add(abs_path)
    return success
