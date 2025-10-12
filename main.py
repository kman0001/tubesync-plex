import logging
from pathlib import Path
from core.ffmpeg_setup import setup_ffmpeg
from core.watchdog_handler import start_watchdog
from core.video_processor import run_processing
from core.settings import config, DISABLE_WATCHDOG

def main():
    setup_ffmpeg()

    base_dirs = []
    for lib_id in config.get("PLEX_LIBRARY_IDS", []):
        try:
            section = plex.library.sectionByID(lib_id)
        except Exception:
            continue
        base_dirs.extend(getattr(section, "locations", []))

    if DISABLE_WATCHDOG:
        logging.info("[MAIN] Running initial full processing (watchdog disabled)")
        run_processing(base_dirs)
    elif config.get("WATCH_FOLDERS", False):
        logging.info("[MAIN] Starting Watchdog mode")
        start_watchdog(base_dirs)

    logging.info("END")

if __name__ == "__main__":
    main()
