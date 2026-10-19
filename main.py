import os
import requests
import asyncio
import edge_tts
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
from config import GEMINI_API_KEY, MINIMAX_API_KEY, PIXABAY_API_KEY, BGM_PATH, VIDEO_FPS, VIDEO_PRESET, VIDEO_THREADS

# ============================================================
# 1. Pixabay 무료 잔잔한 배경음악 자동 다운로드 (Sub BGM)
# ============================================================
def get_ambient_sub_bgm() -> str:
    sub_bgm_path = "assets/audio/sub_ambient_bgm.mp3"
    
    # 이미 다운로드된 잔잔한 서브 BGM이 있다면 재사용
    if os.path.exists(sub_bgm_path):
        return sub_bgm_path

    os.makedirs("assets/audio", exist_ok=True)
    try:
        print("🎵 [Pixabay] 대사 연출용 잔잔한 서브 배경음악 다운로드 중...")
        url = f"https://pixabay.com/api/audio/?key={PIXABAY_API_KEY}&q=ambient+clockwork+soft&per_page=3"
        res = requests.get(url, timeout=15).json()
        
        if res.get("hits"):
            audio_url = res["hits"][0]["audio"]
            a_res = requests.get(audio_url, timeout=30)
            with open(sub_bgm_path, "wb") as f:
                f.write(a_res.content)
            return sub_bgm_path
    except Exception as e:
        print(f"⚠️ 서브 BGM 다운로드 실패 (메인 BGM 잔잔하게 대체): {e}")
    
    return BGM_PATH  # 실패 시 메인 BGM으로 대체

# ============================================================
# 2. 오프닝/클로징/하이라이트 & 잔잔한 BGM 다이내믹 조합
# ============================================================
def build_multi_track_bgm(main_bgm_path: str, sub_bgm_path: str, scene_timings: list, total_scene_duration: float):
    audio_tracks = []
    
    # 메인 업로드 BGM 로드
    main_bgm = AudioFileClip(main_bgm_path) if os.path.exists(main_bgm_path) else None
    
    # 서브 잔잔한 BGM 로드 (없을 경우 메인 BGM 사용)
    sub_bgm_file = sub_bgm_path if os.path.exists(sub_bgm_path) else main_bgm_path
    sub_bgm = AudioFileClip(sub_bgm_file) if os.path.exists(sub_bgm_file) else None

    # [1] 오프닝 BGM (0초~5초): 업로드한 메인 BGM (볼륨 30%)
    if main_bgm:
        open_audio = main_bgm.with_section((0, min(5.0, main_bgm.duration))).with_start(0.0).with_volume_scaling(0.30)
        audio_tracks.append(open_audio)

    # [2] 본문 씬별 BGM 분기 처리 (하이라이트 vs 일반 잔잔한 BGM)
    for timing in scene_timings:
        # 오프닝 5초 offset 적용
        start_t = timing["start"] + 5.0
        end_t = timing["end"] + 5.0
        dur = end_t - start_t

        if timing["is_highlight"] and main_bgm:
            print(f"🔥 Scene {timing['scene_id']} [하이라이트 씬] - 업로드 메인 BGM 강하게 배치!")
            # 메인 BGM의 하이라이트 구간(30초 지점부터) 슬라이싱 사용
            hl_offset = 30.0 if main_bgm.duration >= (30.0 + dur) else 0.0
            clip = main_bgm.with_section((hl_offset, hl_offset + dur)).with_start(start_t).with_volume_scaling(0.35)
            audio_tracks.append(clip)
        elif sub_bgm:
            # 일반 대사 씬: 대사가 잘 들리도록 잔잔한 서브 BGM 배치 (볼륨 8%)
            sub_offset = (timing["start"] % (sub_bgm.duration - dur)) if sub_bgm.duration > dur else 0.0
            clip = sub_bgm.with_section((sub_offset, sub_offset + dur)).with_start(start_t).with_volume_scaling(0.08)
            audio_tracks.append(clip)

    # [3] 클로징 BGM (마지막 5초): 업로드한 메인 BGM (볼륨 30%)
    closing_start_t = total_scene_duration + 5.0
    if main_bgm:
        close_audio = main_bgm.with_section((0, min(5.0, main_bgm.duration))).with_start(closing_start_t).with_volume_scaling(0.30)
        audio_tracks.append(close_audio)

    return CompositeAudioClip(audio_tracks) if audio_tracks else None

# ============================================================
# 3. 최종 통합 및 인코딩 함수
# ============================================================
def build_final_episode(season: int, episode: int, script_data: dict, audio_clips: list, scene_timings: list, total_scene_duration: float):
    print("🎞️ 오프닝-본문-클로징 및 다이내믹 BGM 트랙 오디오 합성 시작...")
    video_clips = []

    # 1. AI 오프닝 (5초)
    generate_video_file(script_data.get("opening_prompt"), "opening.mp4")
    if os.path.exists("opening.mp4"):
        video_clips.append(VideoFileClip("opening.mp4").subclip(0, 5))

    # 2. 본문 씬 결합 (Crossfade)
    for idx in range(len(script_data["scenes"])):
        fpath = f"scene_{idx + 1}.mp4"
        if os.path.exists(fpath):
            clip = VideoFileClip(fpath).crossfadein(0.5).crossfadeout(0.5)
            video_clips.append(clip)

    # 3. AI 클로징 (5초)
    generate_video_file(script_data.get("ending_prompt"), "ending.mp4")
    if os.path.exists("ending.mp4"):
        video_clips.append(VideoFileClip("ending.mp4").subclip(0, 5))

    if not video_clips:
        print("❌ 결합할 비디오 클립이 없습니다.")
        return

    final_video_clip = concatenate_videoclips(video_clips, method="compose", padding=-0.3)

    # 4. 서브 BGM 준비 및 트랙별 배경음악 조합
    sub_bgm_path = get_ambient_sub_bgm()
    combined_bgm = build_multi_track_bgm(BGM_PATH, sub_bgm_path, scene_timings, total_scene_duration)

    # 5. 오프닝 5초 offset 적용된 TTS 성우 음성
    tts_audio_list = []
    for clip in audio_clips:
        tts_audio_list.append(clip.with_start(clip.start + 5.0))

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
    print(f"✨ 대사 전달력 극대화 렌더링 완벽 완료: {output_filename}")
