#!/usr/bin/env python3
import logging
from settings.base import load_settings
from core.ffmpeg import ensure_ffmpeg
from core.cache import load_cache
from watchers.filesystem import start_watchdog
from watchers.scheduler import start_periodic_cache_save

def main():
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

    config = load_settings()
    logging.info("[INIT] Configuration loaded")

    ensure_ffmpeg()
    logging.info("[INIT] FFmpeg ready")

    load_cache()
    start_periodic_cache_save(interval=60)

    start_watchdog(config)
    logging.info("[RUNNING] Watchdog started")

if __name__ == "__main__":
    main()
