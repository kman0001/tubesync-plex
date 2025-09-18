import subprocess, os
from utils import VIDEO_EXTS

LANG_MAP = {"eng":"en","jpn":"ja","kor":"ko","fre":"fr","fra":"fr","spa":"es","ger":"de","deu":"de","ita":"it","chi":"zh","und":"und"}

def map_lang(code):
    return LANG_MAP.get(code.lower(),"und")

def extract_subtitles(video_path):
    base, _ = os.path.splitext(video_path)
    srt_files = []
    ffprobe_cmd = ["ffprobe","-v","error","-select_streams","s",
                   "-show_entries","stream=index:stream_tags=language,codec_name",
                   "-of","json", video_path]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True)
        streams = json.loads(result.stdout).get("streams", [])
        for s in streams:
            idx = s.get("index")
            lang = map_lang(s.get("tags", {}).get("language", "und"))
            srt = f"{base}.{lang}.srt"
            if os.path.exists(srt):
                continue
            subprocess.run(["ffmpeg","-y","-i",video_path,"-map",f"0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(srt):
                srt_files.append((srt, lang))
    except:
        pass
    return srt_files

def upload_subtitles(plex_item, srt_files):
    for srt, lang in srt_files:
        try:
            plex_item.uploadSubtitles(srt, language=lang)
        except:
            continue
