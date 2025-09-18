import platform, os, shutil, subprocess
from pathlib import Path

def setup_ffmpeg(base_dir, detail=False):
    FFMPEG_BIN = base_dir / "ffmpeg"
    arch = platform.machine()
    if arch == "x86_64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
    elif arch == "aarch64":
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
    else:
        print(f"[ERROR] Unsupported architecture: {arch}")
        exit(1)

    tmp_dir = Path("/tmp/ffmpeg_download")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(f"curl -L {url} | tar -xJ -C {tmp_dir}", shell=True, check=True)

    ffmpeg_path = next(tmp_dir.glob("**/ffmpeg"), None)
    ffprobe_path = next(tmp_dir.glob("**/ffprobe"), None)
    if ffmpeg_path:
        shutil.move(str(ffmpeg_path), FFMPEG_BIN)
        os.chmod(FFMPEG_BIN, 0o755)
    if ffprobe_path:
        shutil.move(str(ffprobe_path), FFMPEG_BIN.parent / "ffprobe")
        os.chmod(str(FFMPEG_BIN.parent / "ffprobe"), 0o755)

    os.environ["PATH"] = f"{FFMPEG_BIN.parent}:{os.environ.get('PATH','')}"
    if detail:
        print("[INFO] FFmpeg/FFprobe ready")
