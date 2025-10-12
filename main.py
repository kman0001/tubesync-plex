import logging
from pathlib import Path
from core.ffmpeg import setup_ffmpeg
from core.processing import run_processing
from core.watchdog import start_watchdog

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Example config
PLEX_LIBRARY_PATHS = ["./media"]  # 실제 Plex library 폴더 경로
DISABLE_WATCHDOG = True           # False로 설정하면 Watchdog 모드

def main():
    setup_ffmpeg()
    base_dirs = [Path(p) for p in PLEX_LIBRARY_PATHS]

    if DISABLE_WATCHDOG:
        logging.info("[MAIN] Running full processing (watchdog disabled)")
        run_processing(base_dirs)
    else:
        logging.info("[MAIN] Starting Watchdog mode")
        start_watchdog(base_dirs)

    logging.info("[MAIN] Done")

if __name__ == "__main__":
    main()
