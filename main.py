#!/usr/bin/env python3
import logging
from settings.base import load_config, BASE_DIR
from core.ffmpeg import setup_ffmpeg
from core.cache import load_cache, save_cache
from core.plex import connect_plex
from watchers.filesystem import start_watchdog
from watchers.scheduler import start_repair_scheduler

def main():
    # 1️⃣ 설정 로드
    config = load_config()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")

    # 2️⃣ Plex 연결
    plex = connect_plex(config)
    logging.info("[MAIN] Connected to Plex successfully")

    # 3️⃣ ffmpeg 준비
    setup_ffmpeg()

    # 4️⃣ 캐시 로드
    cache = load_cache()
    logging.info(f"[CACHE] Loaded {len(cache)} entries")

    # 5️⃣ 감시 시작
    if config.get("WATCH_FOLDERS", False):
        start_watchdog(config, plex, cache)
    else:
        logging.info("[MAIN] Watchdog disabled, running manual scan")
        start_repair_scheduler(config, plex, cache)

    # 종료 시 캐시 저장
    save_cache(cache)
    logging.info("[MAIN] Exiting gracefully")

if __name__ == "__main__":
    main()
