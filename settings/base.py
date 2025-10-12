import os, json
from pathlib import Path

BASE_DIR = Path(os.getenv("BASE_DIR", "/app"))
CONFIG_PATH = Path(os.getenv("CONFIG_FILE", BASE_DIR / "settings/config.json"))
CACHE_FILE = BASE_DIR / "data/tubesync_cache.json"
FFMPEG_BIN = BASE_DIR / "venv/bin/ffmpeg"
FFPROBE_BIN = BASE_DIR / "venv/bin/ffprobe"

def load_settings():
    """Load JSON config file with runtime settings"""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")
