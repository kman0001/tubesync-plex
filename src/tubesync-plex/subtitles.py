import subprocess
from pathlib import Path

VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".m4v")
LANG_MAP = {
    "eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr",
    "spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"
}

def map_lang(code):
    return LANG_MAP.get(code.lower(), "und")

def extract_subtitles(video_path):
    base, _ = os.path.splitext(video_path)
    srt_files = []
    ffprobe_cmd = ["ffprobe","-v","error","-select_streams","s","-show_entries",
                   "stream=index:stream_tags=language,codec_name","-of","json", video_path]
    try:
        import json
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags", {}).get("language", "und"))
            srt = f"{base}.{lang}.srt"
            if Path(srt).exists(): continue
            subprocess.run(["ffmpeg","-y","-i",video_path,"-map",f"0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            srt_files.append((srt, lang))
    except Exception:
        pass
    return srt_files

def upload_subtitles(ep, srt_files, api_semaphore, request_delay):
    import time
    for srt, lang in srt_files:
        try:
            with api_semaphore:
                ep.uploadSubtitles(srt, language=lang)
                time.sleep(request_delay)
        except Exception:
            pass
