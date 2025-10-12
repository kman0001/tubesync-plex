#!/usr/bin/env python3
import sys
import logging
from pathlib import Path

from core.ffmpeg_manager import setup_ffmpeg
from core.scanner import scan_and_update_cache, scan_nfo_files
from core.video_processor import run_processing
from core.watchdog import start_watchdog
from core.plex_helper import plex, get_base_dirs
from core.settings import CONFIG_FILE, config, DISABLE_WATCHDOG

# ==============================
# Main Execution
# ==============================
def main():
    # FFmpeg 설치/업데이트
    setup_ffmpeg()

    # Plex 라이브러리 경로 가져오기
    base_dirs = get_base_dirs(config)

    if DISABLE_WATCHDOG:
        logging.info("[MAIN] Running initial full processing (watchdog disabled)")
        run_processing(base_dirs)
    elif config.get("WATCH_FOLDERS", False):
        logging.info("[MAIN] Starting Watchdog mode")
        start_watchdog(base_dirs)

    logging.info("END")


if __name__ == "__main__":
    main()
