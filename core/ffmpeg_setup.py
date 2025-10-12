import os
import platform
import shutil
from pathlib import Path
import logging
import requests

def setup_ffmpeg(base_dir: Path, ffmpeg_bin: Path, ffprobe_bin: Path, ffmpeg_version_file: Path):
    arch = platform.machine()
    base_url = f"https://raw.githubusercontent.com/kman0001/tubesync-plex/main/ffmpeg/{arch}"

    ffmpeg_url = f"{base_url}/ffmpeg"
    ffprobe_url = f"{base_url}/ffprobe"
    version_url = f"{base_url}/version.txt"

    tmp_dir = Path("/tmp/ffmpeg_dl")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tar_ffmpeg = tmp_dir / "ffmpeg"
    tar_ffprobe = tmp_dir / "ffprobe"

    remote_version = None
    try:
        r = requests.get(version_url, timeout=10)
        r.raise_for_status()
        remote_version = r.text.strip()
        logging.info(f"Remote FFmpeg version: {remote_version}")
    except Exception as e:
        logging.warning(f"Failed to fetch version info: {e}")
        return

    local_version = None
    if ffmpeg_version_file.exists():
        local_version = ffmpeg_version_file.read_text().strip()

    if ffmpeg_bin.exists() and ffprobe_bin.exists() and local_version == remote_version:
        logging.info(f"FFmpeg already up-to-date ({local_version})")
        return

    for f in (ffmpeg_bin, ffprobe_bin):
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

    ok1 = download_file(ffmpeg_url, tar_ffmpeg)
    ok2 = download_file(ffprobe_url, tar_ffprobe)
    if not (ok1 and ok2):
        logging.error("Failed to download one or more FFmpeg binaries.")
        return

    try:
        shutil.move(str(tar_ffmpeg), ffmpeg_bin)
        shutil.move(str(tar_ffprobe), ffprobe_bin)
        os.chmod(ffmpeg_bin, 0o755)
        os.chmod(ffprobe_bin, 0o755)
        if remote_version:
            ffmpeg_version_file.write_text(remote_version)
    except Exception as e:
        logging.error(f"FFmpeg install failed: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    logging.info("✅ FFmpeg installed/updated successfully")
