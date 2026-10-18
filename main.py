import os
import time
import asyncio
import edge_tts
import yt_dlp
from google import genai

# MoviePy v2.0+ 최신 임포트 규격
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# ----------------------------------------------------
# 1. API 키 초기화
# ----------------------------------------------------
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise Exception("❌ API 키가 설정되지 않았습니다. Secrets를 확인하세요.")

client = genai.Client(api_key=api_key)

# ----------------------------------------------------
# 2. AI 대본 생성 (503 트래픽 과부하 및 404 구형 모델 종료 방어)
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
            print(f"  ⚠️ {model_name} 일시 오류: {e} ({wait_time}초 후 자동 재시도)")
            time.sleep(wait_time)
            
    if script_text:
        break

if not script_text:
    raise Exception("❌ Gemini API 대본 생성 실패: 모든 백업 모델 요청이 거부되었습니다.")

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
# 4. 유튜브 CC 영상 다운로드 (JS Challenge / Cookie / Format 예외 종합 방어)
# ----------------------------------------------------
print("3. 유튜브 CC 영상 다운로드 중...")

cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
cookie_file_path = None

if cookies_content.strip():
    cookie_file_path = "cookies.txt"
    with open(cookie_file_path, "w", encoding="utf-8") as f:
        f.write(cookies_content)
    print("  ✓ YOUTUBE_COOKIES 적용 완료!")

search_queries = [
    "ytsearch1:nature 4k relax creative commons",
    "ytsearch1:galaxy space 4k creative commons",
    "ytsearch1:ocean waves 4k creative commons"
]

format_strategies = ['best', 'bestvideo+bestaudio/best', 'worst']
download_success = False

for query in search_queries:
    for fmt in format_strategies:
        ydl_opts = {
            'default_search': query,
            'format': fmt,
            'merge_output_format': 'mp4',
            'outtmpl': 'background.mp4',
            'overwrites': True,
            'quiet': True,
            'cookiefile': cookie_file_path if cookie_file_path else None,
            'extractor_args': {
                'youtube': {
                    'player_client': ['mweb', 'web']
                }
            }
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([query])
            if os.path.exists("background.mp4") and os.path.getsize("background.mp4") > 0:
                download_success = True
                print(f"  ✓ 배경 영상 다운로드 성공 (전략: {fmt})")
                break
        except Exception as e:
            print(f"  ⚠️ 다운로드 차단/포맷 에러 우회 시도 중... ({e})")
            continue
            
    if download_success:
        break

if cookie_file_path and os.path.exists(cookie_file_path):
    os.remove(cookie_file_path)

if not download_success:
    raise Exception("❌ 영상 다운로드 실패: 모든 대체 키워드 및 포맷 전략 실패")

# ----------------------------------------------------
# 5. 영상 + 음성 + 자막 합성 (MoviePy v2.0+ 호환 규격)
# ----------------------------------------------------
print("4. 쇼츠 영상 합성 중...")

audio = AudioFileClip("voice.mp3")
full_video = VideoFileClip("background.mp4")

# v2.0 규격 대응: subclip -> subclipped
start_time = 10 if full_video.duration > (audio.duration + 10) else 0
if hasattr(full_video, "subclipped"):
    video = full_video.subclipped(start_time, start_time + audio.duration)
else:
    video = full_video.subclip(start_time, start_time + audio.duration)

# MoviePy v2.0 자막 생성 대응
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
    # 하위 버전/호환 파라미터 Fallback
    txt_clip = TextClip(
        script_text, 
        fontsize=35, 
        color='white', 
        bg_color='black', 
        size=(int(video.w * 0.8), None), 
        method='caption', 
        font='NanumGothic'
    )

# v2.0 규격 대응: set_position / set_duration / set_audio
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

# 메모리 정리
audio.close()
full_video.close()
video.close()
final_video.close()

print("✨ [성공] 모든 에러 방어 및 쇼츠 파일(final_shorts.mp4) 생성 완료!")
