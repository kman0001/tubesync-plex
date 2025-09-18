import json
from pathlib import Path
from .utils import ensure_path

BASE_DIR = Path("/app")
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

default_config = {
    "_comment": {
        "plex_base_url": "Base URL of your Plex server (e.g., http://localhost:32400).",
        "plex_token": "Your Plex authentication token.",
        "plex_library_ids": "List of Plex library IDs to sync (e.g., [10,21,35]).",
        "silent": "true = only summary logs, false = detailed logs",
        "detail": "true = verbose mode (debug output)",
        "subtitles": "true = extract and upload subtitles",
        "threads": "Number of worker threads for initial scanning",
        "max_concurrent_requests": "Max concurrent Plex API requests",
        "request_delay": "Delay between Plex API requests (sec)",
        "watch_folders": "true = enable real-time folder monitoring",
        "watch_debounce_delay": "Debounce time (sec) before processing events"
    },
    "plex_base_url": "",
    "plex_token": "",
    "plex_library_ids": [],
    "silent": False,
    "detail": False,
    "subtitles": False,
    "threads": 8,
    "max_concurrent_requests": 4,
    "request_delay": 0.1,
    "watch_folders": False,
    "watch_debounce_delay": 2,
    "cache": {}
}

def load_config(config_path, disable_watchdog=False):
    CONFIG_FILE = Path(config_path)
    CACHE_FILE = CONFIG_FILE.parent / "tubesync_cache.json"

    if not CONFIG_FILE.exists():
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"[INFO] {CONFIG_FILE} created. Please edit and rerun.")
        exit(0)

    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        config = json.load(f)

    if disable_watchdog:
        config["watch_folders"] = False

    # ensure cache file exists
    ensure_path(CACHE_FILE.parent)
    if not CACHE_FILE.exists():
        CACHE_FILE.write_text("{}")

    return config, CONFIG_FILE, CACHE_FILE
