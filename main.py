import logging
from pathlib import Path
from core.ffmpeg import setup_ffmpeg
from core.processing import run_processing
from core.watchdog import start_watchdog
from core.config import config

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

DISABLE_WATCHDOG = True  # False로 설정하면 Watchdog 모드

def main():
    setup_ffmpeg()

    # Plex library locations
    base_dirs = []
    for lib_path in config.get("PLEX_LIBRARY_IDS", []):
        base_dirs.append(Path(lib_path))  # 실제 폴더 경로로 바꿔야 함

    if DISABLE_WATCHDOG:
        logging.info("[MAIN] Running full processing (watchdog disabled)")
        run_processing(base_dirs)
    else:
        logging.info("[MAIN] Starting Watchdog mode")
        start_watchdog(base_dirs)

    logging.info("[MAIN] Done")

if __name__ == "__main__":
    main()
