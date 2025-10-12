import json
import os
from pathlib import Path


BASE_DIR = Path(os.getenv("BASE_DIR", str(Path(__file__).resolve().parents[1])))
CONFIG_FILE = Path(os.getenv("CONFIG_FILE", BASE_DIR / "settings/config.json"))
CACHE_FILE = CONFIG_FILE.parent / "tubesync_cache.json"


DEFAULT_CONFIG = {
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
"ALWAYS_APPLY_NFO": False,
"DELETE_NFO_AFTER_APPLY": True,
"CACHE_REPAIR_INTERVAL": 300,
"DELAY_AFTER_NEW_FILE": 60,
}




def load_default_config(path=CONFIG_FILE):
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("w", encoding="utf-8") as f:
json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)




def load_config():
if not CONFIG_FILE.exists():
load_default_config()
print(f"[INFO] Created default config at {CONFIG_FILE}. Edit it and re-run.")
raise SystemExit(0)


with CONFIG_FILE.open("r", encoding="utf-8") as f:
return json.load(f)
