#!/usr/bin/env python3
"""Entry point for tubesync_plex."""
import logging
import signal
import sys
from pathlib import Path


from settings.base import load_config, BASE_DIR
from core.ffmpeg import setup_ffmpeg
from core.cache import load_cache, save_cache
from core.plex import connect_plex
from watchers.filesystem import start_watchdog, run_once_process
from watchers.scheduler import start_periodic_cache_save, start_repair_scheduler


LOGGER = logging.getLogger("tubesync.main")




def _setup_logging(detail=False, silent=False):
level = logging.DEBUG if detail else (logging.WARNING if silent else logging.INFO)
fmt = '[%(asctime)s] [%(levelname)s] %(message)s'
logging.basicConfig(level=level, format=fmt, datefmt='%Y-%m-%d %H:%M:%S')




def main():
config = load_config()
_setup_logging(detail=config.get("DETAIL", False), silent=config.get("SILENT", False))


LOGGER.info("[MAIN] Starting tubesync_plex")


# Connect to Plex
plex = connect_plex(config.get("PLEX_BASE_URL"), config.get("PLEX_TOKEN"), debug_http=config.get("DEBUG_HTTP", False))


# Ensure ffmpeg
setup_ffmpeg()


# Load cache
cache = load_cache()
LOGGER.info(f"[CACHE] Loaded {len(cache)} entries")


# Start periodic cache save thread
start_periodic_cache_save(interval=60)


# Start repair scheduler (background rescheduler for missing ratingKeys)
start_repair_scheduler(interval=config.get("CACHE_REPAIR_INTERVAL", 300))


# Run either Watchdog or single run
if config.get("WATCH_FOLDERS", False) and not config.get("DISABLE_WATCHDOG", False):
# Turn config library ids into concrete paths via Plex
base_dirs = []
for lib_id in config.get("PLEX_LIBRARY_IDS", []):
try:
section = plex.library.sectionByID(lib_id)
base_dirs.extend(getattr(section, "locations", []))
except Exception:
continue
if not base_dirs:
LOGGER.warning("No library locations found from Plex. Make sure PLEX_LIBRARY_IDS is correct.")
start_watchdog(base_dirs)
else:
LOGGER.info("[MAIN] Running single processing pass (watchdog disabled)")
# Get base dirs from plex sections
base_dirs = []
for lib_id in config.get("PLEX_LIBRARY_IDS", []):
try:
section = plex.library.sectionByID(lib_id)
base_dirs.extend(getattr(section, "locations", []))
except Exception:
continue
if not base_dirs:
LOGGER.warning("No library locations found — provide WATCH_PATHS in config or set PLEX_LIBRARY_IDS correctly.")
run_once_process(base_dirs)


# graceful shutdown handlers
def _exit(sig, frame):
LOGGER.info("[MAIN] Shutting down... saving cache")
save_cache()
sys.exit(0)


signal.signal(signal.SIGINT, _exit)
signal.signal(signal.SIGTERM, _exit)




if __name__ == "__main__":
main()
