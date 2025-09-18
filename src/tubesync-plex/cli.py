#!/usr/bin/env python3
import sys, time, logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from watchdog.observers import Observer

from tubesync_plex.config import load_config, BASE_DIR, save_cache
from tubesync_plex.plex_client import PlexServerWithHTTPDebug
from tubesync_plex.ffmpeg_utils import setup_ffmpeg
from tubesync_plex.metadata import scan_and_update_cache, process_file
from tubesync_plex.watcher import VideoEventHandler

def main():
    parser = argparse.ArgumentParser(description="TubeSync Plex Metadata")
    parser.add_argument("--config", required=True, help="Path to config file")
    parser.add_argument("--disable-watchdog", action="store_true", help="Disable folder monitoring")
    parser.add_argument("--detail", action="store_true", help="Enable detailed logs")
    parser.add_argument("--debug-http", action="store_true", help="Enable HTTP debug logging")
    args = parser.parse_args()

    # -----------------------------
    # Load config & setup logging
    # -----------------------------
    config, CONFIG_FILE, CACHE_FILE = load_config(args.config, args.disable_watchdog)
    silent = config.get("silent", False)
    detail = config.get("detail", False) and not silent
    log_level = logging.INFO if not silent else logging.WARNING
    logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

    # -----------------------------
    # Setup FFmpeg
    # -----------------------------
    setup_ffmpeg(BASE_DIR, detail)

    # -----------------------------
    # Connect to Plex
    # -----------------------------
    try:
        plex = PlexServerWithHTTPDebug(config["plex_base_url"], config["plex_token"], debug_http=args.debug_http)
    except Exception as e:
        logging.error(f"Failed to connect to Plex: {e}")
        sys.exit(1)

    # -----------------------------
    # Scan libraries and update cache
    # -----------------------------
    scan_and_update_cache(plex, config)
    save_cache()

    # -----------------------------
    # Process files concurrently
    # -----------------------------
    total = 0
    with ThreadPoolExecutor(max_workers=config.get("threads", 4)) as ex:
        futures = {ex.submit(process_file, path, plex, config): path for path in config.get("cache", {})}
        for fut in as_completed(futures):
            if fut.result():
                total += 1

    if not silent:
        print(f"[INFO] Total items updated: {total}")

    save_cache()

    # -----------------------------
    # Start Watchdog if enabled
    # -----------------------------
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
