import os, json
from pathlib import Path

BASE_DIR = Path(os.getenv("BASE_DIR", str(Path(__file__).resolve().parents[1])))

CONFIG_FILE = Path(os.getenv("CONFIG_FILE", BASE_DIR / "settings/config.json"))
CACHE_FILE = CONFIG_FILE.parent / "tubesync_cache.json"

# 기본 설정값
DEFAULT_CONFIG = {
    "PLEX_BASE_URL": "",
    "PLEX_TOKEN": "",
    "PLEX_LIBRARY_IDS": [],
    "SILENT": False,
    "DETAIL": False,
    "SUBTITLES": False,
    "THREADS": 8,
    "MAX_CONCURRENT_REQUESTS": 4,
    "REQUEST_DELAY": 0.2,
    "WATCH_FOLDERS": False,
    "WATCH_DEBOUNCE_DELAY": 3,
    "ALWAYS_APPLY_NFO": False,
    "DELETE_NFO_AFTER_APPLY": True
}

def load_config():
    """Load config.json (create if missing)"""
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        print(f"[INFO] Created default config at {CONFIG_FILE}. Please edit and rerun.")
        exit(0)

    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)
