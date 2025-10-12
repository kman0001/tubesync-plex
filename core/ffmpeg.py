"""
FFmpeg installer & helper. Uses the same logic as your original script but wrapped as a module.
"""
import os
import shutil
import platform
import requests
import logging
from pathlib import Path
from settings.base import BASE_DIR


LOGGER = logging.getLogger("tubesync.ffmpeg")


VENVDIR = BASE_DIR / "venv"
FFMPEG_BIN = VENVDIR / "bin/ffmpeg"
FFPROBE_BIN = VENVDIR / "bin/ffprobe"
FFMPEG_VERSION_FILE = BASE_DIR / ".ffmpeg_version"




def setup_ffmpeg():
"""Ensure ffmpeg and ffprobe exist. Attempt to download if absent.
This implementation keeps behavior similar to your original function but avoids hard failures.
"""
arch = platform.machine()
base_url = f"https://raw.githubusercontent.com/kman0001/tubesync-plex/main/ffmpeg/{arch}"


ffmpeg_url = f"{base_url}/ffmpeg"
ffprobe_url = f"{base_url}/ffprobe"
version_url = f"{base_url}/version.txt"


tmp_dir = Path("/tmp/ffmpeg_dl")
tmp_dir.mkdir(parents=True, exist_ok=True)


tar_ffmpeg = tmp_dir / "ffmpeg"
tar_ffprobe = tmp_dir / "ffprobe"


shutil.rmtree(tmp_dir, ignore_errors=True)
