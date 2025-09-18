import logging
import threading
import time
from pathlib import Path

log_lock = threading.Lock()

def setup_logging(silent=False, detail=False):
    log_level = logging.INFO if not silent else logging.WARNING
    logging.basicConfig(level=log_level, format='[%(levelname)s] %(message)s')
    return detail

def safe_print(msg):
    """Thread-safe print"""
    with log_lock:
        print(msg)

def sleep_delay(sec):
    """Thread-safe sleep"""
    time.sleep(sec)

def ensure_path(path):
    """Ensure directory exists"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
