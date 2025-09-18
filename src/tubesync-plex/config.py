import json
from pathlib import Path

BASE_DIR = Path("/app")

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
    config_file = Path(config_path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    if not config_file.exists():
        with config_file.open("w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"[INFO] {config_file} created. Please edit it and rerun.")
        exit(0)

    with config_file.open("r", encoding="utf-8") as f:
        config = json.load(f)

    if disable_watchdog:
        config["watch_folders"] = False

    cache_file = config_file.parent / "tubesync_cache.json"
    if cache_file.exists():
        try:
            with cache_file.open("r", encoding="utf-8") as f:
                config["cache"] = json.load(f)
        except:
            config["cache"] = {}
    else:
        config["cache"] = {}

    return config, config_file, cache_file

def save_cache(config):
    cache_file = BASE_DIR / "config" / "tubesync_cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(config.get("cache", {}), f, indent=2, ensure_ascii=False)
