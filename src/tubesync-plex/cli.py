#!/usr/bin/env python3
import argparse
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from watchdog.observers import Observer

# ==============================
# 내부 모듈 import
# ==============================
from tubesync_plex.config import load_config, BASE_DIR
from tubesync_plex.plex_client import PlexServerWithHTTPDebug
from tubesync_plex.ffmpeg_utils import setup_ffmpeg
from tubesync_plex.metadata import process_file, scan_and_update_cache, save_cache
from tubesync_plex.watcher import VideoEventHandler

# ==============================
# Main CLI entry
# ==============================
def main():
    # ------------------------------
    # Argument parsing
    # ------------------------------
    parser = argparse.ArgumentParser(description="TubeSync Plex Metadata")
    parser.add_argument("--config", required=True, help="Path to config file")
    parser.add_argument("--disable-watchdog", action="store_true", help="Disable real-time folder monitoring")
    parser.add_argument("--detail", action="store_true", help="Enable detailed debug logs")
    parser.add_argument("--debug-http", action="store_true", help="Enable HTTP debug logging for Plex requests")
    args = parser.parse_args()

    # ------------------------------
    # Load configuration and cache
    # ------------------------------
    config, CONFIG_FILE, CACHE_FILE = load_config(args.config, args.disable_watchdog)

    # ------------------------------
    # Logging setup
    # ------------------------------
    silent = config.get("silent", False)
    detail = config.get("detail", False) and not silent
    log_level = logging.INFO if not silent else logging.WARNING
    logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')

    # ------------------------------
    # FFmpeg setup
    # ------------------------------
    setup_ffmpeg(BASE_DIR, detail)

    # ------------------------------
    # Connect to Plex
    # ------------------------------
    try:
        plex = PlexServerWithHTTPDebug(
            config["plex_base_url"],
            config["plex_token"],
            debug_http=args.debug_http
        )
    except Exception as e:
        logging.error(f"Failed to connect to Plex: {e}")
        sys.exit(1)

    # ------------------------------
    # Scan Plex libraries and update cache
    # ------------------------------
    scan_and_update_cache(plex, config)
    save_cache()

    # ------------------------------
    # Process existing video files using ThreadPool
    # ------------------------------
    total = 0
    cache_keys = list(config.get("cache", {}).keys())  # cache dict 내부 key 목록
    with ThreadPoolExecutor(max_workers=config.get("threads", 4)) as executor:
        futures = {executor.submit(process_file, path, plex, config): path for path in cache_keys}
        for fut in as_completed(futures):
            if fut.result():
                total += 1

    if not silent:
        print(f"[INFO] Total items updated: {total}")

    save_cache()

    # ------------------------------
    # Start Watchdog for real-time folder monitoring
    # ------------------------------
    if config.get("watch_folders", False) and not args.disable_watchdog:
        observer = Observer()
        handler = VideoEventHandler(plex, config)
        for lib_id in config["plex_library_ids"]:
            try:
                section = plex.library.sectionByID(lib_id)
            except Exception:
                continue
            for path in getattr(section, "locations", []):
                observer.schedule(handler, path, recursive=True)

        observer.start()
        print("[INFO] Watchdog started. Monitoring file changes...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("[INFO] Stopping watchdog...")
            observer.stop()
        observer.join()

# ==============================
# Entry point
# ==============================
if __name__ == "__main__":
    main()
