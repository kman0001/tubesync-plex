import os
import platform
import shutil
from pathlib import Path
import requests
import logging

BASE_DIR = Path(__file__).parent.parent
VENVDIR = BASE_DIR / "venv"
FFMPEG_BIN = VENVDIR / "bin/ffmpeg"
FFPROBE_BIN = VENVDIR / "bin/ffprobe"
FFMPEG_VERSION_FILE = BASE_DIR / ".ffmpeg_version"

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")

def setup_ffmpeg():
    arch = platform.machine()
    base_url = f"https://raw.githubusercontent.com/kman0001/tubesync-plex/main/ffmpeg/{arch}"

    ffmpeg_url = f"{base_url}/ffmpeg"
    ffprobe_url = f"{base_url}/ffprobe"
    version_url = f"{base_url}/version.txt"

    tmp_dir = Path("/tmp/ffmpeg_dl")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    remote_version = None
    try:
        r = requests.get(version_url, timeout=10)
        r.raise_for_status()
        remote_version = r.text.strip()
        logging.info(f"Remote FFmpeg version: {remote_version}")
    except Exception as e:
        logging.warning(f"Failed to fetch version info from GitHub: {e}")
        return

    local_version = None
    if FFMPEG_VERSION_FILE.exists():
        local_version = FFMPEG_VERSION_FILE.read_text().strip()

    if (
        FFMPEG_BIN.exists()
        and FFPROBE_BIN.exists()
        and local_version == remote_version
    ):
        logging.info(f"FFmpeg already up-to-date ({local_version})")
        return

    for f in (FFMPEG_BIN, FFPROBE_BIN):
        if f.exists():
            f.unlink()

    def download_file(url, path):
        try:
            r = requests.get(url, stream=True, timeout=60)
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            logging.info(f"Downloaded {url}")
            return True
        except Exception as e:
            logging.error(f"Failed to download {url}: {e}")
            return False

    ok1 = download_file(ffmpeg_url, tmp_dir / "ffmpeg")
    ok2 = download_file(ffprobe_url, tmp_dir / "ffprobe")
    if not (ok1 and ok2):
        logging.error("Failed to download one or more FFmpeg binaries.")
        return

    try:
        shutil.move(str(tmp_dir / "ffmpeg"), FFMPEG_BIN)
        shutil.move(str(tmp_dir / "ffprobe"), FFPROBE_BIN)
        os.chmod(FFMPEG_BIN, 0o755)
        os.chmod(FFPROBE_BIN, 0o755)
        if remote_version:
            FFMPEG_VERSION_FILE.write_text(remote_version)
    except Exception as e:
        logging.error(f"FFmpeg move/install failed: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    logging.info("✅ FFmpeg installed/updated successfully")
