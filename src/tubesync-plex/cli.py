import argparse, sys, time, logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from tubesync_plex.config import load_config, BASE_DIR
from tubesync_plex.plex_client import PlexServerWithHTTPDebug
from tubesync_plex.ffmpeg_utils import setup_ffmpeg
from tubesync_plex.metadata import process_file, scan_and_update_cache, save_cache
from tubesync_plex.watcher import VideoEventHandler
from watchdog.observers import Observer

def main():
    parser = argparse.ArgumentParser(description="TubeSync Plex Metadata")
    parser.add_argument("--config", required=True, help="Path to config file")
    parser.add_argument("--disable-watchdog", action="store_true")
    parser.add_argument("--detail", action="store_true")
    parser.add_argument("--debug-http", action="store_true")
    args = parser.parse_args()

    config, CONFIG_FILE, CACHE_FILE = load_config(args.config, args.disable_watchdog)

    silent = config.get("silent", False)
    detail = config.get("detail", False) and not silent
    log_level = logging.INFO if not silent else logging.WARNING
    logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

    setup_ffmpeg(BASE_DIR, detail)

    try:
        plex = PlexServerWithHTTPDebug(config["plex_base_url"], config["plex_token"], debug_http=args.debug_http)
    except Exception as e:
        logging.error(f"Failed to connect to Plex: {e}")
        sys.exit(1)

    scan_and_update_cache(plex, config)
    save_cache()

    total = 0
    with ThreadPoolExecutor(max_workers=config.get("threads", 4)) as ex:
        futures = {ex.submit(process_file, f, plex, config): f for f in []}  # cache.keys() 연결 필요
        for fut in as_completed(futures):
            if fut.result():
                total += 1

    if not silent:
        print(f"[INFO] Total items updated: {total}")

    save_cache()

    if config.get("watch_folders", False) and not args.disable_watchdog:
        observer = Observer()
        handler = VideoEventHandler(plex, config)
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except Exception:
                continue
            for p in getattr(section, "locations", []):
                observer.schedule(handler, p, recursive=True)

        observer.start()
        print("[INFO] Watchdog started. Monitoring file changes...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

if __name__ == "__main__":
    main()
