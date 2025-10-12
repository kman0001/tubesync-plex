from plexapi.server import PlexServer
from pathlib import Path
import logging

plex = None  # PlexServer instance; initialized in main

def init_plex(base_url, token):
    global plex
    try:
        plex = PlexServer(base_url, token)
        logging.info("[PLEX] Connected successfully")
    except Exception as e:
        logging.error(f"[PLEX] Failed to connect: {e}")
        plex = None

def find_plex_item(abs_path):
    abs_path = os.path.abspath(abs_path)
    for lib_id in plex.library.sectionIDs():
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue

        section_type = getattr(section, "TYPE", None) or getattr(section, "type", "")
        section_type = str(section_type).lower()
        if section_type == "show":
            results = section.search(libtype="episode")
        elif section_type in ("movie", "video"):
            results = section.search(libtype="movie")
        else:
            results = section.search()

        for item in results:
            parts_iter = []
            try:
                parts_iter = item.iterParts()
            except Exception:
                try:
                    parts_iter = getattr(item, "parts", []) or []
                except Exception:
                    parts_iter = []

            for part in parts_iter:
                try:
                    if os.path.abspath(part.file) == abs_path:
                        return item
                except Exception:
                    continue
    return None
