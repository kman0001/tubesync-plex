import os, platform, shutil, subprocess
from pathlib import Path
from .utils import safe_print

def setup_ffmpeg(base_dir, detail=False):
    FFMPEG_BIN = base_dir / "ffmpeg"
    FFMPEG_SHA_FILE = base_dir / ".ffmpeg_sha"

    arch = platform.machine()
    if arch == "x86_64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif arch == "aarch64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else:
        safe_print(f"[ERROR] Unsupported architecture: {arch}")
        exit(1)

    tmp_dir = Path("/tmp/ffmpeg_download")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(f"curl -L {url} | tar -xJ -C {tmp_dir}", shell=True, check=True)
    except subprocess.CalledProcessError as e:
        safe_print(f"[ERROR] FFmpeg download failed: {e}")
        return

    ffmpeg_path = next(tmp_dir.glob("**/ffmpeg"), None)
    ffprobe_path = next(tmp_dir.glob("**/ffprobe"), None)

    if ffmpeg_path:
        shutil.move(str(ffmpeg_path), FFMPEG_BIN)
        os.chmod(FFMPEG_BIN, 0o755)
    if ffprobe_path:
        shutil.move(str(ffprobe_path), FFMPEG_BIN.parent / "ffprobe")
        os.chmod(str(FFMPEG_BIN.parent / "ffprobe"), 0o755)

    os.environ["PATH"] = f"{FFMPEG_BIN.parent}:{os.environ.get('PATH','')}"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    if detail:
        safe_print("[INFO] FFmpeg/FFprobe setup complete.")
