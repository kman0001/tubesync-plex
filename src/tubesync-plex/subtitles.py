import subprocess
from pathlib import Path
from .utils import safe_print, sleep_delay

LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr",
            "spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}

def map_lang(code):
    return LANG_MAP.get(code.lower(), "und")

def extract_subtitles(video_path):
    base = Path(video_path).with_suffix("")
    srt_files = []
    try:
        cmd = ["ffprobe","-v","error","-select_streams","s","-show_entries",
               "stream=index:stream_tags=language,codec_name","-of","json", video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        import json
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags", {}).get("language", "und"))
            srt = f"{base}.{lang}.srt"
            if Path(srt).exists():
                continue
            subprocess.run(["ffmpeg","-y","-i",video_path,f"-map","0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if Path(srt).exists():
                srt_files.append((srt, lang))
    except Exception as e:
        safe_print(f"[ERROR] Subtitle extraction failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep, srt_files, semaphore, delay, detail=False):
    for srt, lang in srt_files:
        try:
            with semaphore:
                ep.uploadSubtitles(srt, language=lang)
                sleep_delay(delay)
            if detail:
                safe_print(f"[SUBTITLE] Uploaded: {srt}")
        except Exception as e:
            safe_print(f"[ERROR] Subtitle upload failed: {srt} - {e}")
