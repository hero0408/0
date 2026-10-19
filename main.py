import os
import sys
import json
import time
import requests
import asyncio
import traceback
import edge_tts
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips

from config import GEMINI_API_KEY, MINIMAX_API_KEY, PIXABAY_API_KEY, BGM_PATH, VIDEO_FPS, VIDEO_PRESET, VIDEO_THREADS
from prompts import build_system_prompt_for_script

# ============================================================
# 1. Gemini AI 대본 생성 (자동 재시도 및 로깅 강화)
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
            print(f"⚠️ 대본 생성 시도 {attempt + 1} 실패: {e}")
            time.sleep(2)

    print("⚠️ 대본 생성 실패로 백업 대본 구조를 사용합니다.")
    return {
        "season": season, "episode": episode, "title": "시간 보관소의 시작",
        "opening_prompt": "Antique brass clockwork background Pixar style 9:16 --",
        "ending_prompt": "Peaceful clock room sunset Pixar style 9:16 --",
        "scenes": [
            {
                "scene_id": 1,
                "narration": "시침이 멈춘 시간 보관소에 소중한 아침이 찾아옵니다.",
                "video_prompt": "A fluffy silver baby fox walking in antique clockwork room Pixar style 9:16 --",
                "is_highlight": False
            }
        ]
    }

# ============================================================
# 2. 비디오 씬 생성 (MiniMax + Pixabay 백업)
# ============================================================
def generate_video_file(prompt: str, output_name: str, max_retries: int = 2) -> str:
    enhanced_prompt = f"{prompt}, smooth motion, natural body animation, 24fps"
    print(f"🎬 비디오 생성 중: {output_name}")

    for attempt in range(max_retries):
        try:
            url = "https://api.minimaxi.chat/v1/video_generation"
            headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"}
            payload = {"prompt": enhanced_prompt, "model": "video-01", "aspect_ratio": "9:16"}

            res = requests.post(url, headers=headers, json=payload, timeout=30)
            if res.status_code == 200 and "video_url" in res.json():
                v_res = requests.get(res.json()["video_url"], timeout=60)
                with open(output_name, "wb") as f:
                    f.write(v_res.content)
                print(f"✅ 비디오 생성 성공: {output_name}")
                return output_name
        except Exception as e:
            print(f"⚠️ {output_name} 생성 시도 {attempt + 1} 실패: {e}")
            time.sleep(2)

    # 백업 다운로드 로직
    try:
        print(f"🔄 {output_name} Pixabay 백업 소스 다운로드 전환")
        fb_url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q=clockwork+fantasy&orientation=vertical"
        res = requests.get(fb_url, timeout=15).json()
        if res.get("hits"):
            backup_url = res["hits"][0]["videos"]["medium"]["url"]
            v_res = requests.get(backup_url, timeout=30)
            with open(output_name, "wb") as f:
                f.write(v_res.content)
            print(f"✅ 백업 비디오 다운로드 완료: {output_name}")
            return output_name
    except Exception as e:
        print(f"❌ 백업 영상 다운로드도 실패했습니다: {e}")

    return output_name

# ============================================================
# 3. Pixabay 무료 서브 BGM 자동 다운로드
# ============================================================
def get_ambient_sub_bgm() -> str:
    sub_bgm_path = "assets/audio/sub_ambient_bgm.mp3"
    if os.path.exists(sub_bgm_path):
        return sub_bgm_path

    os.makedirs("assets/audio", exist_ok=True)
    try:
        print("🎵 [Pixabay] 서브 배경음악 다운로드 중...")
        url = f"https://pixabay.com/api/audio/?key={PIXABAY_API_KEY}&q=ambient+clockwork+soft&per_page=3"
        res = requests.get(url, timeout=15).json()
        if res.get("hits"):
            audio_url = res["hits"][0]["audio"]
            a_res = requests.get(audio_url, timeout=30)
            with open(sub_bgm_path, "wb") as f:
                f.write(a_res.content)
            return sub_bgm_path
    except Exception as e:
        print(f"⚠️ 서브 BGM 다운로드 실패 (메인 BGM 대체): {e}")

    return BGM_PATH

# ============================================================
# 4. TTS 성우 음성 생성
# ============================================================
async def generate_audio_tracks(scenes: list):
    audio_clips = []
    scene_timings = []
    current_time = 0.0

    for idx, scene in enumerate(scenes):
        audio_file = f"tts_{idx + 1}.mp3"
        try:
            print(f"🗣️ TTS 음성 생성 중: Scene {idx + 1}")
            comm = edge_tts.Communicate(scene["narration"], "ko-KR-SunHiNeural", rate="-5%", pitch="-1Hz")
            await comm.save(audio_file)

            clip = AudioFileClip(audio_file).with_start(current_time)
            audio_clips.append(clip)

            duration = max(clip.duration + 0.8, 4.0)
            scene_timings.append({
                "scene_id": idx + 1,
                "start": current_time,
                "end": current_time + duration,
                "is_highlight": scene.get("is_highlight", False)
            })
            current_time += duration
        except Exception as e:
            print(f"⚠️ Scene {idx + 1} TTS 오류: {e}")

    return audio_clips, scene_timings, current_time

# ============================================================
# 5. 오프닝/클로징/하이라이트 다이내믹 BGM 트랙 조합
# ============================================================
def build_multi_track_bgm(main_bgm_path: str, sub_bgm_path: str, scene_timings: list, total_scene_duration: float):
    audio_tracks = []
    main_bgm = AudioFileClip(main_bgm_path) if os.path.exists(main_bgm_path) else None
    sub_file = sub_bgm_path if os.path.exists(sub_bgm_path) else main_bgm_path
    sub_bgm = AudioFileClip(sub_file) if os.path.exists(sub_file) else None

    # 오프닝 5초 BGM (볼륨 30%)
    if main_bgm:
        open_audio = main_bgm.with_section((0, min(5.0, main_bgm.duration))).with_start(0.0).with_volume_scaling(0.30)
        audio_tracks.append(open_audio)

    # 씬별 BGM (하이라이트 vs 서브 BGM)
    for timing in scene_timings:
        start_t = timing["start"] + 5.0
        end_t = timing["end"] + 5.0
        dur = end_t - start_t

        if timing["is_highlight"] and main_bgm:
            hl_offset = 30.0 if main_bgm.duration >= (30.0 + dur) else 0.0
            clip = main_bgm.with_section((hl_offset, hl_offset + dur)).with_start(start_t).with_volume_scaling(0.35)
            audio_tracks.append(clip)
        elif sub_bgm:
            sub_offset = (timing["start"] % (sub_bgm.duration - dur)) if sub_bgm.duration > dur else 0.0
            clip = sub_bgm.with_section((sub_offset, sub_offset + dur)).with_start(start_t).with_volume_scaling(0.08)
            audio_tracks.append(clip)

    # 클로징 5초 BGM (볼륨 30%)
    closing_start_t = total_scene_duration + 5.0
    if main_bgm:
        close_audio = main_bgm.with_section((0, min(5.0, main_bgm.duration))).with_start(closing_start_t).with_volume_scaling(0.30)
        audio_tracks.append(close_audio)

    return CompositeAudioClip(audio_tracks) if audio_tracks else None

# ============================================================
# 6. 최종 비디오/오디오 결합 및 파일 저장
# ============================================================
def build_final_episode(season: int, episode: int, script_data: dict, audio_clips: list, scene_timings: list, total_scene_duration: float):
    print("🎞️ 오프닝-본문-클로징 및 오디오 최종 인코딩 합성 중...")
    video_clips = []

    # AI 오프닝 (5초)
    generate_video_file(script_data.get("opening_prompt"), "opening.mp4")
    if os.path.exists("opening.mp4"):
        video_clips.append(VideoFileClip("opening.mp4").subclip(0, 5))

    # 본문 씬 결합
    for idx in range(len(script_data["scenes"])):
        fpath = f"scene_{idx + 1}.mp4"
        if os.path.exists(fpath):
            clip = VideoFileClip(fpath).crossfadein(0.5).crossfadeout(0.5)
            video_clips.append(clip)

    # AI 클로징 (5초)
    generate_video_file(script_data.get("ending_prompt"), "ending.mp4")
    if os.path.exists("ending.mp4"):
        video_clips.append(VideoFileClip("ending.mp4").subclip(0, 5))

    if not video_clips:
        raise RuntimeError("❌ 인코딩할 비디오 클립 파일이 전혀 존재하지 않습니다.")

    final_video_clip = concatenate_videoclips(video_clips, method="compose", padding=-0.3)

    sub_bgm_path = get_ambient_sub_bgm()
    combined_bgm = build_multi_track_bgm(BGM_PATH, sub_bgm_path, scene_timings, total_scene_duration)

    tts_audio_list = [clip.with_start(clip.start + 5.0) for clip in audio_clips]
    all_audio = tts_audio_list
    if combined_bgm:
        all_audio.insert(0, combined_bgm)

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
    print(f"✨ 영상 렌더링 완벽 완료: {output_filename}")

# ============================================================
# 7. 메인 실행 함수
# ============================================================
def run_pipeline(season: int = 1, episode: int = 1):
    print(f"🚀 [Pipeline Started] Season {season} - Episode {episode}")

    script_data = generate_script(season, episode)
    scenes = script_data.get("scenes", [])

    for idx, scene in enumerate(scenes):
        generate_video_file(scene["video_prompt"], f"scene_{idx + 1}.mp4")

    audio_clips, scene_timings, total_duration = asyncio.run(generate_audio_tracks(scenes))
    build_final_episode(season, episode, script_data, audio_clips, scene_timings, total_duration)

# ============================================================
# 8. 메인 진입점 (명시적 에러 로깅 처리)
# ============================================================
if __name__ == "__main__":
    try:
        print("🚀 [Main Entry] 파이프라인 프로세스 가동 시작")
        season_input = int(os.getenv("SEASON", 1))
        episode_input = int(os.getenv("EPISODE", 1))

        run_pipeline(season=season_input, episode=episode_input)
        print("🎉 [Pipeline Success] 모든 작업이 정상 완료되었습니다.")
    except Exception as err:
        print("❌ [Fatal Error] 메인 파이프라인 구동 중 심각한 오류 발생:")
        print(err)
        traceback.print_exc()
        sys.exit(1) # GitHub Actions에 명시적 실패 상태 전달
