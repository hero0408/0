import os
import re
import json
import asyncio
import logging
import urllib.request
from typing import List
from dataclasses import dataclass

import edge_tts
# MoviePy v2 최신 호환 서브모듈 직접 임포트
from moviepy.VideoClip import VideoFileClip, ColorClip
from moviepy.AudioClip import AudioFileClip, CompositeAudioClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
from moviepy.video.fx import CrossFadeIn, CrossFadeOut
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut

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
# 1. Gemini REST API (Structured JSON 대본 생성)
# ==========================================
def generate_script_via_gemini(api_key: str) -> EpisodeScript:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompt = """
    Create a short 3D animation script for 'The Clockwork Time Repository'.
    Characters: Ein (Silver Fox), Chrono (Tiger), Escape (Rabbit).
    Generate JSON with the exact following schema:
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
    Generate exactly 3 lines of dialogue. Return raw valid JSON ONLY.
    """
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    
    with urllib.request.urlopen(req) as response:
        res_data = json.loads(response.read().decode('utf-8'))
        raw_text = res_data['candidates'][0]['content']['parts'][0]['text']
        cleaned_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
        data = json.loads(cleaned_text)
        
        return EpisodeScript(
            title_ko=data['title_ko'],
            title_en=data['title_en'],
            title_ja=data['title_ja'],
            lines=[ScriptLine(**l) for l in data['lines']]
        )

# ==========================================
# 2. Edge-TTS 음성 동기 합성
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
# 3. MoviePy v2 영상/음성 렌더링 Engine
# ==========================================
def render_full_episode(base_video_path: str, audio_files: List[str], output_path: str):
    # 1) 오프닝 / 클로징 가공 (파일 미존재 시 자가 복구)
    if not os.path.exists(config.OPENING_PATH):
        logger.warning(f"{config.OPENING_PATH} 파일이 없어 더미 오프닝을 생성합니다.")
        ColorClip(size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(15, 10, 30), duration=3.0).write_videofile(config.OPENING_PATH, fps=config.FPS)
    if not os.path.exists(config.CLOSING_PATH):
        logger.warning(f"{config.CLOSING_PATH} 파일이 없어 더미 클로징을 생성합니다.")
        ColorClip(size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(10, 10, 20), duration=3.0).write_videofile(config.CLOSING_PATH, fps=config.FPS)

    opening_clip = VideoFileClip(config.OPENING_PATH).subclipped(0, 3.0).with_effects([CrossFadeIn(0.5)])
    closing_clip = VideoFileClip(config.CLOSING_PATH).subclipped(0, 3.0).with_effects([CrossFadeOut(0.5)])
    
    body_video = VideoFileClip(base_video_path)
    
    # 2) 대사 오디오 트랙 타임라인 정렬 및 사운드 페이드 효과
    audio_clips = []
    current_time = 0.5
    for a_file in audio_files:
        clip = AudioFileClip(a_file).with_effects([AudioFadeIn(0.05), AudioFadeOut(0.05)]).with_start(current_time)
        audio_clips.append(clip)
        current_time += clip.duration + 0.4
        
    composite_audio = CompositeAudioClip(audio_clips)
    
    # 3) 본문 영상 동기화
    body_duration = max(body_video.duration, composite_audio.duration + 0.5)
    body_video = body_video.subclipped(0, body_duration).with_audio(composite_audio)
    
    # 4) 오프닝 + 본문 + 클로징 시퀀스 연결
    final_video = concatenate_videoclips([opening_clip, body_video, closing_clip], method="compose")
    
    # 5) 최종 파일 인코딩
    final_video.write_videofile(
        output_path,
        fps=config.FPS,
        codec='libx264',
        audio_codec='aac',
        temp_audiofile='temp-render-track.m4a',
        remove_temp=True,
        threads=4
    )
    
    # 6) 메모리 명시적 해제
    opening_clip.close()
    closing_clip.close()
    body_video.close()
    composite_audio.close()
    for ac in audio_clips:
        ac.close()
    final_video.close()

# ==========================================
# 4. 파이프라인 메인 실행 루틴
# ==========================================
async def async_main():
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
        
    logger.info("[1/4] Gemini REST API로 대본 생성 중...")
    script = generate_script_via_gemini(config.GEMINI_API_KEY)
    
    with open(config.METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump({"title_ko": script.title_ko, "title_en": script.title_en, "title_ja": script.title_ja}, f, ensure_ascii=False, indent=2)

    if not os.path.exists(config.BASE_VIDEO_PATH):
        logger.warning(f"{config.BASE_VIDEO_PATH}가 존재하지 않아 플레이스홀더 영상을 생성합니다.")
        color_clip = ColorClip(size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(20, 20, 35), duration=10.0)
        color_clip.write_videofile(config.BASE_VIDEO_PATH, fps=config.FPS)
        color_clip.close()

    logger.info("[2/4] Edge-TTS 캐릭터 음성 생성 중...")
    audio_files = await generate_tts_files(script.lines)
    
    logger.info(f"[3/4] MoviePy v2 기반 영상 합성 및 렌더링 시작 ({config.OUTPUT_VIDEO_PATH})...")
    render_full_episode(config.BASE_VIDEO_PATH, audio_files, config.OUTPUT_VIDEO_PATH)
    
    # 임시 TTS 파일 정제
    for af in audio_files:
        if os.path.exists(af):
            os.remove(af)

    logger.info("[4/4] YouTube Data API v3 자동 비공개 업로드 실행...")
    if config.YOUTUBE_REFRESH_TOKEN:
        youtube_uploader.upload_private_video(config.OUTPUT_VIDEO_PATH)
    else:
        logger.warning("YOUTUBE_REFRESH_TOKEN이 입력되지 않아 유튜브 업로드를 건너뜁니다.")

    logger.info("파이프라인 실행 완료!")

if __name__ == "__main__":
    asyncio.run(async_main())
