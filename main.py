import os
import re
import json
import time
import asyncio
import logging
import urllib.request
from typing import List
from dataclasses import dataclass

import edge_tts
from moviepy import VideoFileClip, ColorClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
import moviepy.video.fx.all as vfx
import moviepy.audio.fx.all as afx

from config import config
import youtube_uploader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainPipeline")

@dataclass
class ScriptLine:
    character: str
    text_ko: str
    text_en: str
    text_ja: str

@dataclass
class EpisodeScript:
    title_ko: str
    title_en: str
    title_ja: str
    lines: List[ScriptLine]

# ==========================================
# 1. 시즌 고정 오프닝/클로징 캐시 처리 (토큰 소모 0%)
# ==========================================
def ensure_season_intro_outro():
    minimax_key = os.environ.get("MINIMAX_API_KEY")

    if not os.path.exists(config.OPENING_PATH):
        logger.info("시즌 오프닝 파일이 없어 최초 1회 자동 생성을 진행합니다.")
        if minimax_key:
            prompt_op = "A 6-second high-end cinematic 3D animation opening of a gothic clocktower with glowing clockwork gears under a starry night sky with full moon. Golden light, masterpiece, hyper-detailed."
            generate_video_via_minimax(prompt_op, config.OPENING_PATH)
        else:
            logger.warning("MINIMAX_API_KEY가 없어 단색 임시 오프닝을 생성합니다.")
            ColorClip(size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(15, 10, 30), duration=6.0).write_videofile(config.OPENING_PATH, fps=config.FPS)
    else:
        logger.info("기존 시즌 오프닝(opening.mp4)을 재사용합니다.")

    if not os.path.exists(config.CLOSING_PATH):
        logger.info("시즌 클로징 파일이 없어 최초 1회 자동 생성을 진행합니다.")
        if minimax_key:
            prompt_cl = "A 6-second high-end cinematic 3D animation closing scene. Slow pan-out from the glowing clocktower to starry night sky, magical embers fading out peacefully."
            generate_video_via_minimax(prompt_cl, config.CLOSING_PATH)
        else:
            logger.warning("MINIMAX_API_KEY가 없어 단색 임시 클로징을 생성합니다.")
            ColorClip(size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(10, 10, 20), duration=6.0).write_videofile(config.CLOSING_PATH, fps=config.FPS)
    else:
        logger.info("기존 시즌 클로징(closing.mp4)을 재사용합니다.")

def generate_video_via_minimax(prompt: str, output_filepath: str):
    minimax_key = os.environ.get("MINIMAX_API_KEY")
    url = "https://api.minimax.chat/v1/video_generation"
    headers = {"Authorization": f"Bearer {minimax_key}", "Content-Type": "application/json"}
    payload = {"prompt": prompt, "model": "video-01", "aspect_ratio": "9:16"}

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            task_id = res.get("task_id")
            
        query_url = f"https://api.minimax.chat/v1/query/video_generation?task_id={task_id}"
        while True:
            time.sleep(5)
            q_req = urllib.request.Request(query_url, headers=headers, method='GET')
            with urllib.request.urlopen(q_req) as q_res:
                q_data = json.loads(q_res.read().decode('utf-8'))
                if q_data.get("status") == "Success":
                    file_url = q_data.get("file_url")
                    urllib.request.urlretrieve(file_url, output_filepath)
                    logger.info(f"시즌 에셋 비디오 생성 완료: {output_filepath}")
                    break
                elif q_data.get("status") in ["Fail", "Unknown"]:
                    raise Exception("Video generation failed")
    except Exception as e:
        logger.error(f"비디오 생성 예외 발생: {e}")
        ColorClip(size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(15, 10, 30), duration=6.0).write_videofile(output_filepath, fps=config.FPS)

# ==========================================
# 2. Gemini 대본 생성
# ==========================================
def generate_script_via_gemini(api_key: str) -> EpisodeScript:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = """
    Create a short 3D animation script for 'The Clockwork Time Repository'.
    Characters: Ein (Silver Fox), Chrono (Tiger), Escape (Rabbit).
    Return JSON ONLY:
    {
        "title_ko": "시침이 멈춘 시간 보관소",
        "title_en": "The Clockwork Time Repository",
        "title_ja": "針が止まった時間保管所",
        "lines": [
            {"character": "Ein", "text_ko": "보관소의 태엽이 다시 돌아가기 시작했어.", "text_en": "...", "text_ja": "..."},
            {"character": "Chrono", "text_ko": "시간의 궤도를 벗어나지 않도록 주의해라.", "text_en": "...", "text_ja": "..."},
            {"character": "Escape", "text_ko": "늦기 전에 빨리 확인하러 가자!", "text_en": "...", "text_ja": "..."}
        ]
    }
    """
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"response_mime_type": "application/json"}}
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    
    with urllib.request.urlopen(req) as response:
        res_data = json.loads(response.read().decode('utf-8'))
        cleaned_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", res_data['candidates'][0]['content']['parts'][0]['text'].strip(), flags=re.MULTILINE)
        data = json.loads(cleaned_text)
        return EpisodeScript(title_ko=data['title_ko'], title_en=data['title_en'], title_ja=data['title_ja'], lines=[ScriptLine(**l) for l in data['lines']])

# ==========================================
# 3. Edge-TTS 음성 합성
# ==========================================
async def generate_tts_files(lines: List[ScriptLine]) -> List[str]:
    audio_files = []
    for idx, line in enumerate(lines):
        voice = config.VOICE_MAP.get(line.character, 'ko-KR-InJoonNeural')
        output_file = f"temp_dialogue_{idx}.mp3"
        await edge_tts.Communicate(line.text_ko, voice).save(output_file)
        audio_files.append(output_file)
    return audio_files

# ==========================================
# 4. MoviePy v2 합성 Engine
# ==========================================
def render_full_episode(base_video_path: str, audio_files: List[str], output_path: str):
    opening_clip = VideoFileClip(config.OPENING_PATH)
    opening_clip = opening_clip.subclipped(0, min(6.0, opening_clip.duration)).with_effects([vfx.crossfadein(0.5)])
    
    closing_clip = VideoFileClip(config.CLOSING_PATH)
    closing_clip = closing_clip.subclipped(0, min(6.0, closing_clip.duration)).with_effects([vfx.crossfadeout(0.5)])
    
    body_video = VideoFileClip(base_video_path)
    
    audio_clips = []
    current_time = 0.5
    for a_file in audio_files:
        clip = AudioFileClip(a_file).with_effects([afx.audio_fadein(0.05), afx.audio_fadeout(0.05)]).with_start(current_time)
        audio_clips.append(clip)
        current_time += clip.duration + 0.4
        
    composite_audio = CompositeAudioClip(audio_clips)
    body_duration = max(body_video.duration, composite_audio.duration + 0.5)
    body_video = body_video.subclipped(0, body_duration).with_audio(composite_audio)
    
    final_video = concatenate_videoclips([opening_clip, body_video, closing_clip], method="compose")
    
    final_video.write_videofile(
        output_path,
        fps=config.FPS,
        codec='libx264',
        audio_codec='aac',
        temp_audiofile='temp-render-track.m4a',
        remove_temp=True,
        threads=4
    )
    
    opening_clip.close()
    closing_clip.close()
    body_video.close()
    composite_audio.close()
    for ac in audio_clips:
        ac.close()
    final_video.close()

# ==========================================
# 5. 파이프라인 메인 실행
# ==========================================
async def async_main():
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
        
    logger.info("[1/5] 시즌 고정 오프닝/클로징 검사...")
    ensure_season_intro_outro()

    logger.info("[2/5] Gemini 대본 생성...")
    script = generate_script_via_gemini(config.GEMINI_API_KEY)
    
    with open(config.METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump({"title_ko": script.title_ko}, f, ensure_ascii=False, indent=2)

    if not os.path.exists(config.BASE_VIDEO_PATH):
        ColorClip(size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(20, 20, 35), duration=10.0).write_videofile(config.BASE_VIDEO_PATH, fps=config.FPS)

    logger.info("[3/5] TTS 음성 생성...")
    audio_files = await generate_tts_files(script.lines)
    
    logger.info("[4/5] 영상 랜더링 및 오프닝/클로징/본문 합성...")
    render_full_episode(config.BASE_VIDEO_PATH, audio_files, config.OUTPUT_VIDEO_PATH)
    
    for af in audio_files:
        if os.path.exists(af):
            os.remove(af)

    logger.info("[5/5] YouTube 비공개 업로드...")
    if config.YOUTUBE_REFRESH_TOKEN:
        youtube_uploader.upload_private_video(config.OUTPUT_VIDEO_PATH)

    logger.info("파이프라인 실행 성공!")

if __name__ == "__main__":
    asyncio.run(async_main())
