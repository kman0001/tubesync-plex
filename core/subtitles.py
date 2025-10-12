import os
import subprocess
import json
import logging
from core.ffmpeg import FFMPEG_BIN, FFPROBE_BIN, VIDEO_EXTS

def map_lang(lang_code):
    return lang_code if lang_code else "und"

def extract_subtitles(video_path):
    base, _ = os.path.splitext(video_path)
    srt_files=[]
    try:
        result=subprocess.run([str(FFPROBE_BIN),"-v","error","-select_streams","s",
                               "-show_entries","stream=index:stream_tags=language,codec_name",
                               "-of","json",video_path],
                              capture_output=True,text=True,check=True)
        streams=json.loads(result.stdout).get("streams",[])
        for s in streams:
            idx=s.get("index")
            codec=s.get("codec_name","")
            if codec.lower() in ["pgs","dvdsub","hdmv_pgs","vobsub"]:
                logging.warning(f"Skipping unsupported subtitle codec {codec} in {video_path}")
                continue
            lang=map_lang(s.get("tags",{}).get("language","und"))
            srt=f"{base}.{lang}.srt"
            if os.path.exists(srt): continue
            subprocess.run([str(FFMPEG_BIN),"-y","-i",video_path,"-map",f"0:s:{idx}",srt],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
            srt_files.append((srt,lang))
    except Exception as e:
        logging.error(f"[ERROR] Subtitle extraction failed: {video_path} - {e}")
    return srt_files

def upload_subtitles(ep,srt_files, api_semaphore=None, REQUEST_DELAY=0.1):
    for srt,lang in srt_files:
        retries=3
        while retries>0:
            try:
                if api_semaphore:
                    api_semaphore.acquire()
                if hasattr(ep, "uploadSubtitles"):
                    ep.uploadSubtitles(srt, language=lang)
                elif hasattr(ep, "addSubtitles"):
                    ep.addSubtitles(srt, language=lang)
                else:
                    ep.uploadSubtitles(srt, language=lang)
                if api_semaphore:
                    api_semaphore.release()
                break
            except Exception as e:
                retries-=1
                logging.error(f"[ERROR] Subtitle upload failed: {srt} - {e}, retries left: {retries}")
