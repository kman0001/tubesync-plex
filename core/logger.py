import logging
import time

def setup_logging(detail=False, silent=False, debug_http=False):
    # Remove existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    if detail:
        log_level = logging.DEBUG
    elif silent:
        log_level = logging.WARNING
    else:
        log_level = logging.INFO

    logging.basicConfig(
        level=log_level,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True
    )

    if not debug_http:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)

def log_detail(msg, detail=False, silent=False):
    if detail and not silent:
        logging.info(f"[DETAIL] {msg}")

def log_debug(msg, debug=False):
    if debug:
        logging.debug(f"[DEBUG] {msg}")
