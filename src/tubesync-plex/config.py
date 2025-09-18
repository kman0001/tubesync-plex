import json
from pathlib import Path

BASE_DIR = Path("/app")

default_config = {
    "_comment": {
        "plex_base_url": "Base URL of your Plex server",
        "plex_token": "Your Plex authentication token",
        "plex_library_ids": "List of Plex library IDs",
        "silent": "true = only summary logs",
        "detail": "true = verbose mode",
        "subtitles": "true = extract and upload subtitles",
        "threads": "Number of worker threads",
        "max_concurrent_requests": "Max concurrent Plex API requests",
        "request_delay": "Delay between Plex API requests (sec)",
        "watch_folders": "true = enable real-time folder monitoring",
        "watch_debounce_delay": "Debounce time (sec)"
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
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"[INFO] {CONFIG_FILE} created. Edit it and rerun.")
        exit(0)

    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        config = json.load(f)

    if disable_watchdog:
        config["watch_folders"] = False

    if "cache" not in config:
        config["cache"] = {}

    return config, CONFIG_FILE, CACHE_FILE
