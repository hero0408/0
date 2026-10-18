import os
import time
import random
import requests
import asyncio
import edge_tts
from google import genai

# MoviePy v2.0+ 규격 대응
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# ----------------------------------------------------
# 1. API 키 초기화
# ----------------------------------------------------
gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not gemini_key:
    raise Exception("❌ API 키가 설정되지 않았습니다.")

client = genai.Client(api_key=gemini_key)

# ----------------------------------------------------
# 2. AI 대본 생성 (Gemini 3.8 / 3.5 Flash + 예외 처리)
# ----------------------------------------------------
print("1. AI 대본 생성 중...")
prompt = "유튜브 쇼츠용 흥미로운 상식 1가지를 15초 분량(한국어 3~4문장)으로 작성해줘. 응답은 오직 대본 내용만 출력해."

models_to_try = ['gemini-3.8-flash', 'gemini-3.5-flash']
script_text = None

for model_name in models_to_try:
    for attempt in range(5):
        try:
            print(f"  [{model_name}] 대본 요청 중... (시도 {attempt + 1}/5)")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response and response.text:
                script_text = response.text.strip()
                break
        except Exception as e:
            wait_time = (attempt + 1) * 3
            print(f"  ⚠️ {model_name} 일시 오류: {e} ({wait_time}초 후 재시도)")
            time.sleep(wait_time)
            
    if script_text:
        break

if not script_text:
    raise Exception("❌ Gemini API 대본 생성 실패")

print(f"  ✓ 대본 생성 성공: {script_text}")

# ----------------------------------------------------
# 3. 음성 파일 생성 (Edge-TTS)
# ----------------------------------------------------
print("2. 음성 파일 생성 중...")
async def generate_audio():
    communicate = edge_tts.Communicate(script_text, "ko-KR-SunHiNeural")
    await communicate.save("voice.mp3")

asyncio.run(generate_audio())

# ----------------------------------------------------
# 4. Invidious/Piped API 우회 방식을 통한 유튜브 CC 영상 다운로드
# ----------------------------------------------------
print("3. 유튜브 CC 영상 우회 다운로드 중...")

# Invidious 및 Piped 퍼블릭 인스턴스 서버 리스트
INVIDIOUS_INSTANCES = [
    "https://inv.riverside.rocks",
    "https://invidious.nerdvpn.de",
    "https://invidious.flokinet.to",
    "https://invidious.drgns.space",
    "https://vid.puffyan.us"
]

search_query = "nature 4k relax creative commons"
download_success = False

for instance in INVIDIOUS_INSTANCES:
    try:
        print(f"  [인스턴스 시도] {instance}")
        # 1) 영상 검색 요청
        search_url = f"{instance}/api/v1/search?q={search_query}&type=video"
        res = requests.get(search_url, timeout=10)
        
        if res.status_code != 200:
            continue
            
        search_results = res.json()
        if not search_results:
            continue
            
        # 검색결과 중 첫 번째 비디오 ID 추출
        video_id = search_results[0].get("videoId")
        if not video_id:
            continue

        # 2) 비디오 정보 및 직접 다운로드 스트림 URL 추출
        video_info_url = f"{instance}/api/v1/videos/{video_id}"
        info_res = requests.get(video_info_url, timeout=10)
        
        if info_res.status_code != 200:
            continue
            
        info_data = info_res.json()
        format_streams = info_data.get("formatStreams", [])
        
        # mp4 포맷 스트림 찾기
        target_stream_url = None
        for stream in format_streams:
            if stream.get("container") == "mp4":
                target_stream_url = stream.get("url")
                break
                
        if not target_stream_url and format_streams:
            target_stream_url = format_streams[0].get("url")

        if target_stream_url:
            print(f"  ✓ 우회 스트림 URL 확보 성공! 다운로드 시작...")
            video_data = requests.get(target_stream_url, timeout=30)
            with open("background.mp4", "wb") as f:
                f.write(video_data.content)
                
            if os.path.exists("background.mp4") and os.path.getsize("background.mp4") > 0:
                download_success = True
                print("  ✓ 유튜브 CC 배경 영상 우회 다운로드 완벽 성공!")
                break
    except Exception as e:
        print(f"  ⚠️ 인스턴스 우회 실패 ({instance}): {e}")
        continue

if not download_success:
    raise Exception("❌ 유튜브 우회 다운로드 실패: 모든 Invidious 프록시 응답 없음")

# ----------------------------------------------------
# 5. 영상 + 음성 + 자막 합성 (MoviePy v2.0+ 대응)
# ----------------------------------------------------
print("4. 쇼츠 영상 합성 중...")

audio = AudioFileClip("voice.mp3")
full_video = VideoFileClip("background.mp4")

start_time = 3 if full_video.duration > (audio.duration + 3) else 0
if hasattr(full_video, "subclipped"):
    video = full_video.subclipped(start_time, start_time + audio.duration)
else:
    video = full_video.subclip(start_time, start_time + audio.duration)

try:
    txt_clip = TextClip(
        text=script_text, 
        font_size=35, 
        color='white', 
        bg_color='black', 
        size=(int(video.w * 0.8), None), 
        method='caption', 
        font='/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    )
except Exception:
    txt_clip = TextClip(
        script_text, 
        fontsize=35, 
        color='white', 
        bg_color='black', 
        size=(int(video.w * 0.8), None), 
        method='caption', 
        font='NanumGothic'
    )

if hasattr(txt_clip, "with_position"):
    txt_clip = txt_clip.with_position('center').with_duration(audio.duration)
else:
    txt_clip = txt_clip.set_position('center').set_duration(audio.duration)

final_video = CompositeVideoClip([video, txt_clip])

if hasattr(final_video, "with_audio"):
    final_video = final_video.with_audio(audio)
else:
    final_video = final_video.set_audio(audio)

final_video.write_videofile("final_shorts.mp4", fps=24, codec='libx264', audio_codec='aac')

# 메모리 누수 방지
audio.close()
full_video.close()
video.close()
final_video.close()

print("✨ [성공] 유튜브 우회 기반 쇼츠 파일(final_shorts.mp4) 제작 완료!")
