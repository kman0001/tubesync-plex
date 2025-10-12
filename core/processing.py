import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.cache import cache, update_cache, save_cache
from core.nfo import process_nfo
from core.watchdog import VIDEO_EXTS

processed_files = set()
processed_files_lock = threading.Lock()

def process_file(file_path):
    """
    Thread-safe file processing (video + NFO)
    """
    abs_path = Path(file_path).resolve()
    str_path = str(abs_path)

    with processed_files_lock:
        if str_path in processed_files:
            return False
        processed_files.add(str_path)

    try:
        # Process NFO if exists
        nfo_path = abs_path.with_suffix(".nfo")
        if nfo_path.exists():
            process_nfo(str(nfo_path))

        # Update cache for video file
        if abs_path.suffix.lower() in VIDEO_EXTS:
            if str_path not in cache:
                update_cache(str_path)
        return True
    except Exception as e:
        logging.warning(f"[PROCESSING] Failed to process {str_path}: {e}")
        return False

def run_processing(base_dirs, max_workers=4):
    """
    1) Scan video + NFO
    2) Process with ThreadPoolExecutor
    3) Save final cache
    """
    base_dirs = [base_dirs] if isinstance(base_dirs, (str, Path)) else base_dirs

    video_files = []
    nfo_files = []
    for base_dir in base_dirs:
        for root, _, files in os.walk(base_dir):
            for f in files:
                full_path = Path(root) / f
                if full_path.suffix.lower() in VIDEO_EXTS:
                    video_files.append(str(full_path.resolve()))
                elif full_path.suffix.lower() == ".nfo":
                    nfo_files.append(str(full_path.resolve()))

    logging.info(f"[MAIN] {len(video_files)} video files, {len(nfo_files)} NFO files to process.")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # NFO first
        for nfo in nfo_files:
            executor.submit(process_nfo, nfo)
        # Video files
        futures = {executor.submit(process_file, v): v for v in video_files}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                logging.error(f"[MAIN] Failed: {futures[fut]} - {e}")

    save_cache()
    logging.info(f"[CACHE] Final cache saved, {len(cache)} entries")
