#!/usr/bin/env python3
import os
import sys
import logging
from pathlib import Path

from core import ffmpeg, processing, watchdog
from core.plex import plex, get_library_paths
from settings import config

def main():
    ffmpeg.setup_ffmpeg()

    base_dirs = get_library_paths(config)

    if config.get("DISABLE_WATCHDOG", False):
        logging.info("[MAIN] Running initial full processing (watchdog disabled)")
        processing.run_processing(base_dirs)
    elif config.get("WATCH_FOLDERS", False):
        logging.info("[MAIN] Starting Watchdog mode")
        watchdog.start_watchdog(base_dirs)

    logging.info("END")


if __name__ == "__main__":
    main()
