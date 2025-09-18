import os, platform, shutil, subprocess, sys
from pathlib import Path
import requests

def setup_ffmpeg(base_dir, detail=False):
    FFMPEG_BIN = Path(base_dir) / "ffmpeg"
    FFMPEG_SHA_FILE = Path(base_dir) / ".ffmpeg_sha"

    arch = platform.machine()
    if arch == "x86_64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif arch == "aarch64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else:
        print(f"[ERROR] Unsupported architecture: {arch}")
        sys.exit(1)

    sha_url = url + ".sha256"
    remote_sha = None
    try:
        remote_sha = requests.get(sha_url, timeout=10).text.strip().split()[0]
    except Exception as e:
        print(f"[WARN] Failed to fetch FFmpeg SHA: {e}")

    local_sha = None
    if os.path.exists(FFMPEG_SHA_FILE):
        with open(FFMPEG_SHA_FILE, "r") as f:
            local_sha = f.read().strip()

    if os.path.exists(FFMPEG_BIN) and remote_sha and remote_sha == local_sha:
        if detail:
            print("[INFO] FFmpeg up-to-date")
        return

    tmp_dir = Path("/tmp/ffmpeg_download")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(f"curl -L {url} | tar -xJ -C {tmp_dir}", shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to download FFmpeg: {e}")
        if os.path.exists(FFMPEG_BIN):
            return
        sys.exit(1)

    ffmpeg_path = next(tmp_dir.glob("**/ffmpeg"), None)
    if ffmpeg_path:
        shutil.move(str(ffmpeg_path), FFMPEG_BIN)
        os.chmod(FFMPEG_BIN, 0o755)
    ffprobe_path = next(tmp_dir.glob("**/ffprobe"), None)
    if ffprobe_path:
        shutil.move(str(ffprobe_path), FFMPEG_BIN.parent / "ffprobe")
        os.chmod(str(FFMPEG_BIN.parent / "ffprobe"), 0o755)

    if remote_sha:
        with open(FFMPEG_SHA_FILE, "w") as f:
            f.write(remote_sha)

    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.environ["PATH"] = f"{os.path.dirname(FFMPEG_BIN)}:{os.environ.get('PATH','')}"
