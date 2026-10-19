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
import moviepy.video.fx as vfx
import moviepy.audio.fx as afx

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
    video_prompt: str

@dataclass
class EpisodeScript:
    title_ko: str
    title_en: str
    title_ja: str
    lines: List[ScriptLine]

# ==========================================
# 0. 캐릭터별 전용 성우 및 백업 엔진 설정
# ==========================================
ELEVENLABS_VOICES = {
    "Ein": "21m00Tcm4TlvDq8ikWAM",     # 주인공 아인 (감정 연기)
    "Chrono": "VR6AewLTigWG4xT1s5nU"   # 주요 인물 크로노 (감정 연기)
}

FISH_AUDIO_VOICE_ID = "7f92f8efb88f4b26a11751d2f99d6512" # 나레이터 전용 성우 ID

EDGE_TTS_CONFIG = {
    "Escape": {"voice": "ko-KR-HyunsuNeural", "pitch": "+22Hz", "rate": "+15%"}, # 서브 캐릭터
    "Default": {"voice": "ko-KR-InJoonNeural", "pitch": "-2Hz", "rate": "+0%"}    # 나레이터 백업
}

# ==========================================
# 1. API별 음성 합성 함수 (ElevenLabs / Fish Audio / Edge-TTS)
# ==========================================
def generate_elevenlabs_voice(voice_id: str, text: str, output_path: str, api_key: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": api_key}
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    with urllib.request.urlopen(req) as response:
        with open(output_path, 'wb') as f:
            f.write(response.read())

def generate_fish_audio_voice(text: str, output_path: str, api_key: str):
    url = "https://api.fish.audio/v1/tts"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "reference_id": FISH_AUDIO_VOICE_ID,
        "format": "mp3"
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    with urllib.request.urlopen(req) as response:
        with open(output_path, 'wb') as f:
            f.write(response.read())

async def generate_tts_files(lines: List[ScriptLine]) -> List[str]:
    elevenlabs_key = os.environ.get("ELEVENLABS_API_KEY")
    fish_key = os.environ.get("FISH_AUDIO_API_KEY")
    audio_files = []

    for idx, line in enumerate(lines):
        output_file = f"temp_dialogue_{idx}.mp3"
        success = False

        # 1. 나레이션 ➔ Fish Audio 시도
        if line.character == "Narrator" and fish_key:
            try:
                generate_fish_audio_voice(line.text_ko, output_file, fish_key)
                logger.info(f"[{line.character}] Fish Audio 나레이션 음성 생성 완료")
                success = True
            except Exception as e:
                logger.warning(f"Fish Audio 실패 ({e}), 백업 엔진으로 전환합니다.")

        # 2. 주인공 대사 ➔ ElevenLabs 시도
        if not success and line.character in ELEVENLABS_VOICES and elevenlabs_key:
            try:
                v_id = ELEVENLABS_VOICES[line.character]
                generate_elevenlabs_voice(v_id, line.text_ko, output_file, elevenlabs_key)
                logger.info(f"[{line.character}] ElevenLabs 성우 음성 생성 완료")
                success = True
            except Exception as e:
                logger.warning(f"ElevenLabs 실패 ({e}), Edge-TTS로 전환합니다.")

        # 3. 서브 캐릭터 및 Fallback ➔ Edge-TTS 백업
        if not success:
            voice_cfg = EDGE_TTS_CONFIG.get(line.character, EDGE_TTS_CONFIG["Default"])
            communicate = edge_tts.Communicate(text=line.text_ko, voice=voice_cfg["voice"], pitch=voice_cfg["pitch"], rate=voice_cfg["rate"])
            await communicate.save(output_file)
            logger.info(f"[{line.character}] Edge-TTS 음성 합성 완료")

        audio_files.append(output_file)

    return audio_files

# ==========================================
# 2. AI 비디오 생성 (Kling 1순위 ➔ MiniMax 2순위)
# ==========================================
def generate_scene_video(prompt: str, output_filepath: str):
    kling_key = os.environ.get("KLING_API_KEY")
    minimax_key = os.environ.get("MINIMAX_API_KEY")

    if kling_key:
        try:
            logger.info(f"Kling API 비디오 생성 시도: {prompt[:30]}...")
            url = "https://api.klingai.com/v1/videos/text2video"
            headers = {"Authorization": f"Bearer {kling_key}", "Content-Type": "application/json"}
            payload = {"prompt": prompt, "duration": "5", "aspect_ratio": "9:16", "mode": "std"}
            
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode('utf-8'))
                task_id = res.get("data", {}).get("task_id")
                
            query_url = f"https://api.klingai.com/v1/videos/text2video/{task_id}"
            while True:
                time.sleep(5)
                q_req = urllib.request.Request(query_url, headers=headers, method='GET')
                with urllib.request.urlopen(q_req) as q_res:
                    q_data = json.loads(q_res.read().decode('utf-8'))
                    status = q_data.get("data", {}).get("task_status")
                    if status == "succeed":
                        video_url = q_data.get("data", {}).get("task_result", {}).get("videos", [{}])[0].get("url")
                        urllib.request.urlretrieve(video_url, output_filepath)
                        logger.info(f"Kling 비디오 생성 성공: {output_filepath}")
                        return
                    elif status in ["failed", "canceled"]:
                        raise Exception("Kling video generation failed")
        except Exception as e:
            logger.warning(f"Kling API 실패 ({e}). MiniMax API로 전환합니다.")

    if minimax_key:
        try:
            logger.info(f"MiniMax API 비디오 생성 시도: {prompt[:30]}...")
            url = "https://api.minimax.chat/v1/video_generation"
            headers = {"Authorization": f"Bearer {minimax_key}", "Content-Type": "application/json"}
            payload = {"prompt": prompt, "model": "video-01", "aspect_ratio": "9:16"}

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
                        logger.info(f"MiniMax 비디오 생성 성공: {output_filepath}")
                        return
                    elif q_data.get("status") in ["Fail", "Unknown"]:
                        raise Exception("MiniMax video generation failed")
        except Exception as e:
            logger.error(f"MiniMax API 생성 실패: {e}")

    logger.warning("대체 단색 배경을 생성합니다.")
    ColorClip(size=(config.VIDEO_WIDTH, config.VIDEO_HEIGHT), color=(20, 20, 40), duration=5.0).write_videofile(output_filepath, fps=config.FPS)

def ensure_season_intro_outro():
    if not os.path.exists(config.OPENING_PATH):
        logger.info("시즌 오프닝 생성 중...")
        generate_scene_video("A 6-second high-end cinematic 3D animation opening of a gothic clocktower with glowing clockwork gears under a starry night sky with full moon. Golden light, masterpiece, hyper-detailed.", config.OPENING_PATH)

    if not os.path.exists(config.CLOSING_PATH):
        logger.info("시즌 클로징 생성 중...")
        generate_scene_video("A 6-second high-end cinematic 3D animation closing scene. Slow pan-out from the glowing clocktower to starry night sky, magical embers fading out peacefully.", config.CLOSING_PATH)

# ==========================================
# 3. 여운과 몰입감을 주는 대본 프롬프트 (Gemini)
# ==========================================
def generate_script_via_gemini(api_key: str) -> EpisodeScript:
    models = ["gemini-1.5-flash", "gemini-2.0-flash"]
    prompt = """
    Create a thoughtful, narrative-driven 3D animation script for 'The Clockwork Time Repository'.
    
    STORYTELLING GUIDELINES:
    - Provide a complete narrative arc (beginning, conflict, decision, and resolution).
    - Do NOT preach, give moral lessons, or explain what the audience should feel.
    - Let the characters make clear choices in their situation, leaving room for the audience to reflect on the meaning through their own life experiences.

    Return JSON ONLY:
    {
        "title_ko": "멈춰버린 태엽과 마지막 순간",
        "title_en": "The Stopped Mainspring and the Final Moment",
        "title_ja": "止まったゼンマイと最後の瞬間",
        "lines": [
            {
                "character": "Narrator",
                "text_ko": "보관소 가장 깊은 곳, 누군가 가장 소중히 여겼던 '어느 날의 10분'이 담긴 태엽이 멈추려 합니다.",
                "text_en": "Deep inside the repository, a mainspring holding someone's most treasured '10 minutes' is about to stop.",
                "text_ja": "保管所の奥深く、誰かの大切な『ある日の10分』のゼンマイが止まろう meしています。",
                "video_prompt": "3D animation, A delicate glowing clockwork heart slowing down inside a grand gothic clocktower, golden dust particles, highly emotional atmosphere, masterpiece"
            },
            {
                "character": "Ein",
                "text_ko": "이 태엽을 다시 감으면 기억은 영원히 남겠지만... 새로운 시간은 흐르지 않아.",
                "text_en": "If we wind this mainspring again, the memory stays forever... but new time won't flow.",
                "text_ja": "このゼンマイを巻けば記憶は残るけれど、新しい時間は流れない。",
                "video_prompt": "3D animation, Silver fox Ein holding a glowing crystal key near the clockwork heart, looking conflicted with gentle eyes, warm cinematic lighting"
            },
            {
                "character": "Chrono",
                "text_ko": "손을 놓는 것도, 다시 태엽을 감는 것도... 결국 온전히 그의 몫이었지.",
                "text_en": "Letting go or winding it back up... in the end, it was entirely their choice.",
                "text_ja": "手を放すことも、再び巻くことも... 全ては彼自身の 선택이었어.",
                "video_prompt": "3D animation, Brave tiger Chrono standing solemnly beside giant turning gears, warm lantern light, calm and deep atmosphere"
            },
            {
                "character": "Narrator",
                "text_ko": "태엽은 조용히 멈추었고, 그 자리엔 작지만 따뜻한 빛이 피어올랐습니다.",
                "text_en": "The mainspring quietly stopped, and in its place, a small but warm light bloomed.",
                "text_ja": "ゼンマイは quiet に止まり、そこには小さくも温かい光が咲き誇りました。",
                "video_prompt": "3D animation, A peaceful pan-out of the clocktower window as a warm soft light spreads out under a starry night sky, high-end 3D visual"
            }
        ]
    }
    """
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"response_mime_type": "application/json"}}
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                raw_text = res_data['candidates'][0]['content']['parts'][0]['text']
                cleaned_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
                data = json.loads(cleaned_text)
                return EpisodeScript(title_ko=data['title_ko'], title_en=data['title_en'], title_ja=data['title_ja'], lines=[ScriptLine(**l) for l in data['lines']])
        except Exception as e:
            logger.warning(f"Gemini {model} 실패: {e}")
    raise Exception("Gemini 대본 생성 실패")

def get_script_with_fallback() -> EpisodeScript:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            return generate_script_via_gemini(gemini_key)
        except Exception as e:
            logger.warning(f"Gemini 대본 생성 실패: {e}")

    return EpisodeScript(
        title_ko="멈춰버린 태엽과 마지막 순간",
        title_en="The Stopped Mainspring and the Final Moment",
        title_ja="止まったゼンマイと最後の瞬間",
        lines=[
            ScriptLine(character="Narrator", text_ko="보관소 가장 깊은 곳, 누군가 소중히 여겼던 태엽이 멈추려 합니다.", text_en="A mainspring is about to stop.", text_ja="ゼンマイが止まろう me step.", video_prompt="3D animation, Clockwork heart slowing down inside clocktower"),
            ScriptLine(character="Ein", text_ko="이 태엽을 다시 감으면 기억은 남겠지만... 새로운 시간은 흐르지 않아.", text_en="New time won't flow.", text_ja="新しい時間は流れない。", video_prompt="3D animation, Silver fox Ein holding glowing key near clockwork"),
            ScriptLine(character="Chrono", text_ko="손을 놓는 것도, 다시 감는 것도... 온전히 그의 몫이었지.", text_en="It was entirely their choice.", text_ja="全ては彼自身の choices.", video_prompt="3D animation, Tiger Chrono standing near turning gears"),
            ScriptLine(character="Narrator", text_ko="태엽은 조용히 멈추었고, 그 자리엔 작지만 따뜻한 빛이 피어올랐습니다.", text_en="A warm light bloomed.", text_ja="温かい光が咲きました。", video_prompt="3D animation, Warm light spreading under starry night sky")
        ]
    )

# ==========================================
# 4. 멀티 씬 결합 렌더링 Engine
# ==========================================
def render_full_episode_multi_scene(lines: List[ScriptLine], audio_files: List[str], output_path: str):
    opening_clip = VideoFileClip(config.OPENING_PATH)
    opening_duration = min(6.0, opening_clip.duration)
    opening_clip = opening_clip.subclipped(0, opening_duration).with_effects([vfx.CrossFadeIn(0.5)])

    closing_clip = VideoFileClip(config.CLOSING_PATH)
    closing_duration = min(6.0, closing_clip.duration)
    closing_clip = closing_clip.subclipped(0, closing_duration).with_effects([vfx.CrossFadeOut(0.5)])

    body_clips = []
    
    for idx, (line, a_file) in enumerate(zip(lines, audio_files)):
        scene_video_path = f"temp_scene_{idx}.mp4"
        logger.info(f"[{idx+1}/{len(lines)}] 장면 AI 비디오 생성 시도 중...")
        generate_scene_video(line.video_prompt, scene_video_path)

        audio_clip = AudioFileClip(a_file)
        raw_video_clip = VideoFileClip(scene_video_path)

        target_duration = audio_clip.duration + 0.6
        if raw_video_clip.duration < target_duration:
            num_loops = int(target_duration // raw_video_clip.duration) + 1
            adjusted_video = concatenate_videoclips([raw_video_clip] * num_loops).subclipped(0, target_duration)
        else:
            adjusted_video = raw_video_clip.subclipped(0, target_duration)

        adjusted_video = adjusted_video.with_audio(audio_clip)
        body_clips.append(adjusted_video)

    all_clips = [opening_clip] + body_clips + [closing_clip]
    final_video = concatenate_videoclips(all_clips, method="compose")

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
    final_video.close()
    for clip in body_clips:
        clip.close()
    for idx in range(len(lines)):
        s_path = f"temp_scene_{idx}.mp4"
        if os.path.exists(s_path):
            os.remove(s_path)

async def async_main():
    logger.info("[1/5] 오프닝/클로징 검사...")
    ensure_season_intro_outro()

    logger.info("[2/5] 기승전결 서사 대본 생성...")
    script = get_script_with_fallback()

    with open(config.METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump({"title_ko": script.title_ko}, f, ensure_ascii=False, indent=2)

    logger.info("[3/5] 다중 성우 API 음성 생성...")
    audio_files = await generate_tts_files(script.lines)

    logger.info("[4/5] 대사별 AI 영상 생성 및 멀티 씬 합성...")
    render_full_episode_multi_scene(script.lines, audio_files, config.OUTPUT_VIDEO_PATH)

    for af in audio_files:
        if os.path.exists(af):
            os.remove(af)

    logger.info("[5/5] YouTube 비공개 업로드...")
    if config.YOUTUBE_REFRESH_TOKEN:
        youtube_uploader.upload_private_video(config.OUTPUT_VIDEO_PATH)

    logger.info("파이프라인 실행 완료!")

if __name__ == "__main__":
    asyncio.run(async_main())
