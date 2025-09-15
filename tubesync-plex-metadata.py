import os
import json
import time
import threading
from pathlib import Path
from plexapi.server import PlexServer
import lxml.etree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

# -----------------------------
# CONFIG LOAD
# -----------------------------
CONFIG_FILE = os.environ.get("CONFIG_FILE", "config.json")
CONFIG_FILE = os.path.abspath(CONFIG_FILE)

if not os.path.exists(CONFIG_FILE):
    # Create default template if config.json is missing and exit
    template = {
        "_comment": {
            "plex_base_url": "Your Plex server base URL, e.g., http://localhost:32400",
            "plex_token": "Your Plex server token",
            "plex_library_names": "[\"TV Shows\", \"Movies\"]",
            "silent": "true or false",
            "detail": "true or false",
            "subtitles": "true or false",
            "threads": "Number of concurrent threads, e.g., 8",
            "max_concurrent_requests": "Maximum concurrent Plex API requests, e.g., 4",
            "request_delay": "Delay in seconds between Plex API requests, e.g., 0.1"
        },
        "plex_base_url": "",
        "plex_token": "",
        "plex_library_names": [""],
        "silent": False,
        "detail": False,
        "subtitles": False,
        "threads": 8,
        "max_concurrent_requests": 4,
        "request_delay": 0.1
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=4)
    print(f"[INFO] {CONFIG_FILE} created. Please edit it and rerun.")
    exit(0)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

# -----------------------------
# CONNECT TO PLEX
# -----------------------------
try:
    plex = PlexServer(config["plex_base_url"], config["plex_token"])
except Exception as e:
    print(f"[ERROR] Failed to connect to Plex: {e}")
    exit(1)

# -----------------------------
# SETTINGS
# -----------------------------
VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
api_semaphore = threading.Semaphore(config.get("max_concurrent_requests", 2))
request_delay = config.get("request_delay", 0.1)

# Language mapping for subtitles
LANG_MAP = {
    "eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr",
    "spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"
}
def map_lang(code): return LANG_MAP.get(code.lower(),"und")

# -----------------------------
# SUBTITLE EXTRACTION
# -----------------------------
def extract_subtitles(video_path):
    base,_ = os.path.splitext(video_path)
    srt_files=[]
    ffprobe_cmd = ["ffprobe","-v","error","-select_streams","s",
                   "-show_entries","stream=index:stream_tags=language,codec_name",
                   "-of","json",video_path]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True)
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags", {}).get("language", "und"))
            srt = f"{base}.{lang}.srt"
            if os.path.exists(srt): continue
            # Extract subtitle track using ffmpeg
            subprocess.run(["ffmpeg","-y","-i",video_path,f"-map","0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(srt): srt_files.append((srt, lang))
    except Exception as e:
        print(f"[ERROR] ffprobe/ffmpeg failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep, srt_files, detail=False):
    # Upload extracted subtitles to Plex with semaphore control
    for srt, lang in srt_files:
        try:
            with api_semaphore:
                ep.uploadSubtitles(srt, language=lang)
                time.sleep(request_delay)
            if detail: print(f"[SUBTITLE] Uploaded {srt}")
        except Exception as e:
            print(f"[ERROR] Upload subtitle failed {srt}: {e}")

# -----------------------------
# NFO METADATA UPDATE
# -----------------------------
def apply_nfo(ep, file_path, detail=False, subtitles=False):
    # Apply metadata from NFO to Plex episode/movie
    nfo_path = Path(file_path).with_suffix(".nfo")
    if not nfo_path.exists() or nfo_path.stat().st_size == 0: 
        return False
    try:
        tree = ET.parse(str(nfo_path), parser=ET.XMLParser(recover=True))
        root = tree.getroot()
        title = root.findtext("title", "")
        plot = root.findtext("plot", "")
        aired = root.findtext("aired", "")
        if detail: print(f"[-] Applying NFO: {file_path} -> {title}")
        ep.editTitle(title, locked=True)
        ep.editSortTitle(aired, locked=True)
        ep.editSummary(plot, locked=True)
        if subtitles:
            srt_files = extract_subtitles(file_path)
            if srt_files: upload_subtitles(ep, srt_files, detail)
        os.remove(nfo_path)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to apply NFO {nfo_path}: {e}")
        return False

# -----------------------------
# PROCESS SINGLE FILE
# -----------------------------
def process_file(file_path, detail=False, subtitles=False):
    if not file_path.lower().endswith(VIDEO_EXTS): return False
    abs_path = os.path.abspath(file_path)
    found = None

    # Search Plex libraries for corresponding episode/movie
    for lib in config["plex_library_names"]:
        try:
            section = plex.library.section(lib)
        except: continue

        # TV Shows
        if getattr(section, "TYPE", "").lower() == "show":
            for show in section.all():
                for season in getattr(show, "seasons", lambda: [])():
                    for ep in getattr(season, "episodes", lambda: [])():
                        for part in getattr(ep, "iterParts", lambda: [])():
                            if os.path.abspath(part.file) == abs_path:
                                found = ep
                                break
                        if found: break
                    if found: break
                if found: break
        else:  # Movies / Single videos
            for ep in section.all():
                for part in getattr(ep, "iterParts", lambda: [])():
                    if os.path.abspath(part.file) == abs_path:
                        found = ep
                        break
                if found: break

        if found: break

    if not found:
        if config.get("detail", False):
            print(f"[WARN] Episode not found for {file_path}")
        return False
    return apply_nfo(found, abs_path, config.get("detail", False), config.get("subtitles", False))

# -----------------------------
# MAIN
# -----------------------------
def main():
    total = 0
    threads = config.get("threads", 8)
    detail = config.get("detail", False)
    subtitles = config.get("subtitles", False)

    for lib in config["plex_library_names"]:
        try:
            section = plex.library.section(lib)
        except Exception as e:
            print(f"[ERROR] Cannot access library {lib}: {e}")
            continue

        # Determine paths for library
        paths = []
        if hasattr(section, "locations") and section.locations:
            paths = section.locations
        else:
            try:
                paths = [section.path]
            except AttributeError:
                paths = []

        all_files = []
        for p in paths:
            for root, dirs, files in os.walk(p):
                for f in files:
                    all_files.append(os.path.join(root, f))

        if detail: print(f"[INFO] Found {len(all_files)} files in {lib}")

        # ThreadPool processing
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(process_file, f, detail, subtitles) for f in all_files]
            for fut in as_completed(futures):
                if fut.result(): total += 1

    if not config.get("silent", False):
        print(f"[INFO] Total items updated: {total}")

if __name__=="__main__":
    main()
