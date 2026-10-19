import os
import json
import time
import requests
import asyncio
import edge_tts
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips

from config import GEMINI_API_KEY, MINIMAX_API_KEY, PIXABAY_API_KEY, BGM_PATH, VIDEO_FPS, VIDEO_PRESET, VIDEO_THREADS
from prompts import build_system_prompt_for_script

# ============================================================
# 1. Gemini AI 대본 생성 (자동 재시도 & 예외 처리)
# ============================================================
def generate_script(season: int, episode: int, max_retries: int = 3) -> dict:
    prompt_text = build_system_prompt_for_script(season, episode)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }

    for attempt in range(max_retries):
        try:
            print(f"📝 [Gemini] 시즌 {season} - {episode}화 대본 생성 중... (시도 {attempt + 1})")
            res = requests.post(url, headers=headers, json=payload, timeout=45)
            res.raise_for_status()
            text_response = res.json()['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text_response)
        except Exception as e:
            print(f"⚠️ 대본 생성 실패 재시도: {e}")
            time.sleep(2)

    # 전체 API 실패 시 사용하는 백업 구조
    return {
        "season": season,
        "episode": episode,
        "title": "시간 보관소의 하루",
        "scenes": [{
            "scene_id": 1,
            "narration": "시침이 멈춘 시간 보관소에 오늘 하루도 시작됩니다.",
            "video_prompt": "An adorable fluffy silver baby fox named Ain walking, High quality 3D Pixar animated film style, 9:16 vertical ratio --",
            "duration": 10
        }]
    }

# ============================================================
# 2. 비디오 씬 생성 (MiniMax + Pixabay 백업)
# ============================================================
def generate_video_scene(prompt: str, idx: int, max_retries: int = 2) -> str:
    filename = f"scene_{idx + 1}.mp4"
    enhanced_prompt = f"{prompt}, smooth motion, natural body animation, fluid camera transition, 24fps"

    for attempt in range(max_retries):
        try:
            url = "https://api.minimaxi.chat/v1/video_generation"
            headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"}
            payload = {"prompt": enhanced_prompt, "model": "video-01", "aspect_ratio": "9:16"}

            res = requests.post(url, headers=headers, json=payload, timeout=30)
            if res.status_code == 200 and "video_url" in res.json():
                v_res = requests.get(res.json()["video_url"], timeout=60)
                with open(filename, "wb") as f:
                    f.write(v_res.content)
                return filename
        except Exception as e:
            print(f"⚠️ Scene {idx + 1} 비디오 생성 오류 (시도 {attempt + 1}): {e}")
            time.sleep(3)

    # 백업 영상 로직
    try:
        fb_url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q=clockwork+fantasy&orientation=vertical"
        res = requests.get(fb_url, timeout=15).json()
        backup_url = res["hits"][0]["videos"]["medium"]["url"]
        v_res = requests.get(backup_url, timeout=30)
        with open(filename, "wb") as f:
            f.write(v_res.content)
    except Exception as e:
        print(f"❌ Scene {idx + 1} 백업 로드 실패: {e}")

    return filename

# ============================================================
# 3. TTS 음성 생성
# ============================================================
async def generate_audio_tracks(scenes: list):
    audio_clips = []
    current_time = 2.0

    for idx, scene in enumerate(scenes):
        audio_file = f"tts_{idx + 1}.mp3"
        try:
            comm = edge_tts.Communicate(scene["narration"], "ko-KR-SunHiNeural", rate="-5%", pitch="-1Hz")
            await comm.save(audio_file)

            clip = AudioFileClip(audio_file).with_start(current_time)
            audio_clips.append(clip)
            current_time += clip.duration + 0.8
        except Exception as e:
            print(f"⚠️ Scene {idx + 1} TTS 오류: {e}")

    return audio_clips

# ============================================================
# 4. 자연스러운 장면 전환(Crossfade) 및 최종 인코딩
# ============================================================
def build_final_episode(season: int, episode: int, scenes: list, audio_clips: list):
    print("🎞️ 자연스러운 디졸브 전환 적용 및 비디오 최종 인코딩 시작...")
    video_clips = []

    for idx in range(len(scenes)):
        file_path = f"scene_{idx + 1}.mp4"
        if os.path.exists(file_path):
            clip = VideoFileClip(file_path)
            clip = clip.crossfadein(0.5).crossfadeout(0.5)
            video_clips.append(clip)

    if not video_clips:
        print("❌ 결합할 비디오 파일이 존재하지 않습니다.")
        return

    final_video_clip = concatenate_videoclips(video_clips, method="compose", padding=-0.5)
    all_audio = list(audio_clips)

    if os.path.exists(BGM_PATH):
        bgm = AudioFileClip(BGM_PATH).with_section((0, final_video_clip.duration)).with_volume_scaling(0.12)
        all_audio.insert(0, bgm)

    final_audio = CompositeAudioClip(all_audio)
    final_video = final_video_clip.with_audio(final_audio)

    output_filename = f"S{season}_E{episode}_final.mp4"
    final_video.write_videofile(
        output_filename,
        codec="libx264",
        audio_codec="aac",
        fps=VIDEO_FPS,
        preset=VIDEO_PRESET,
        threads=VIDEO_THREADS
    )
    print(f"✨ 렌더링 완료: {output_filename}")

# ============================================================
# 5. 파이프라인 메인 실행
# ============================================================
def run_pipeline(season: int = 1, episode: int = 1):
    print(f"🚀 [Clockwork Repository] 시즌 {season} - {episode}화 랜더링 프로세스 시작")

    # 1. 대본 자동 생성
    script_data = generate_script(season, episode)
    scenes = script_data.get("scenes", [])

    # 2. 비디오 생성
    for idx, scene in enumerate(scenes):
        generate_video_scene(scene["video_prompt"], idx)

    # 3. 오디오 생성
    audio_clips = asyncio.run(generate_audio_tracks(scenes))

    # 4. 결합 및 합성
    build_final_episode(season, episode, scenes, audio_clips)

if __name__ == "__main__":
    # 원하는 시즌과 에피소드 번호를 넣어 실행
    run_pipeline(season=1, episode=1)
