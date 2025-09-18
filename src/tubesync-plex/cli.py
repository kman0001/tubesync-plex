import argparse, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from watchdog.observers import Observer
from threading import Semaphore

from .config import load_config, BASE_DIR
from .plex_client import PlexServerWithHTTPDebug
from .ffmpeg_utils import setup_ffmpeg
from .metadata import process_file, scan_and_update_cache, save_cache
from .watcher import VideoEventHandler
from .utils import setup_logging, safe_print

def main():
    parser = argparse.ArgumentParser(description="TubeSync Plex Metadata")
    parser.add_argument("--config", required=True)
    parser.add_argument("--disable-watchdog", action="store_true")
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--debug-http", action="store_true")
    args = parser.parse_args()

    config, CONFIG_FILE, CACHE_FILE = load_config(args.config, args.disable_watchdog)
    detail = setup_logging(config.get("silent", False), config.get("detail", False))

    setup_ffmpeg(BASE_DIR, detail)

    try:
        plex = PlexServerWithHTTPDebug(config["plex_base_url"], config["plex_token"], debug_http=args.debug_http)
    except Exception as e:
        safe_print(f"[ERROR] Failed to connect to Plex: {e}")
        sys.exit(1)

    cache = {}
    scan_and_update_cache(plex, config, cache)

    total = 0
    semaphore = Semaphore(config.get("max_concurrent_requests",4))
    with ThreadPoolExecutor(max_workers=config.get("threads",4)) as ex:
        futures = {ex.submit(process_file,f,plex,config,cache=cache,semaphore=semaphore): f for f in cache.keys()}
        for fut in as_completed(futures):
            if fut.result():
                total += 1

    safe_print(f"[INFO] Total items updated: {total}")
    save_cache(CACHE_FILE, cache)

    if config.get("watch_folders", False) and not args.disable_watchdog:
        observer = Observer()
        handler = VideoEventHandler(plex, config, cache=cache, semaphore=semaphore)
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except Exception:
                continue
            for p in getattr(section, "locations", []):
                observer.schedule(handler, p, recursive=True)
        observer.start()
        safe_print("[INFO] Watchdog started.")
        try:
            while True: pass
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__ == "__main__":
    main()
