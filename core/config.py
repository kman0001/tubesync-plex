import json
from pathlib import Path
import logging

CONFIG_FILE = Path("config/config.json").resolve()
CACHE_FILE = CONFIG_FILE.parent / "tubesync_cache.json"

# Default config skeleton
default_config = {
    "_comment": {
        "PLEX_BASE_URL": "Base URL of your Plex server (e.g., http://localhost:32400).",
        "PLEX_TOKEN": "Your Plex authentication token.",
        "PLEX_LIBRARY_IDS": "List of Plex library IDs to sync (e.g., [10,21,35]).",
        "SILENT": "true = only summary logs, False = detailed logs",
        "DETAIL": "true = verbose mode (debug output)",
        "SUBTITLES": "true = extract and upload SUBTITLES",
        "THREADS": "Number of worker THREADS for initial scanning",
        "MAX_CONCURRENT_REQUESTS": "Max concurrent Plex API requests",
        "REQUEST_DELAY": "Delay between Plex API requests (sec)",
        "WATCH_FOLDERS": "true = enable real-time folder monitoring",
        "WATCH_DEBOUNCE_DELAY": "Debounce time (sec) before processing events",
        "ALWAYS_APPLY_NFO": "true = always apply NFO metadata regardless of hash",
        "DELETE_NFO_AFTER_APPLY": "true = remove NFO file after applying"
    },
    "PLEX_BASE_URL": "",
    "PLEX_TOKEN": "",
    "PLEX_LIBRARY_IDS": [],
    "SILENT": False,
    "DETAIL": False,
    "SUBTITLES": False,
    "THREADS": 8,
    "MAX_CONCURRENT_REQUESTS": 2,
    "REQUEST_DELAY": 0.1,
    "WATCH_FOLDERS": False,
    "WATCH_DEBOUNCE_DELAY": 2,
    "ALWAYS_APPLY_NFO": True,
    "DELETE_NFO_AFTER_APPLY": True,
}

# Load config
if not CONFIG_FILE.exists():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    logging.info(f"[CONFIG] {CONFIG_FILE} created. Please edit it.")
    raise SystemExit(0)

with CONFIG_FILE.open("r", encoding="utf-8") as f:
    config = json.load(f)
