import os
import requests
import asyncio
import edge_tts
import yt_dlp
from google import genai
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# 1. API 키 설정 (Gemini 3.8 Flash)
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

# 2. AI 대본 생성
print("1. AI 대본 생성 중...")
prompt = "유튜브 쇼츠용 흥미로운 상식 1가지를 15초 분량(한국어 3~4문장)으로 작성해줘. 응답은 오직 대본 내용만 출력해."
response = client.models.generate_content(
    model='gemini-3.8-flash',
    contents=prompt,
)
script_text = response.text.strip()
print(f"대본: {script_text}")

# 3. 음성 파일 생성 (Edge-TTS)
print("2. 음성 파일 생성 중...")
async def generate_audio():
    communicate = edge_tts.Communicate(script_text, "ko-KR-SunHiNeural")
    await communicate.save("voice.mp3")

asyncio.run(generate_audio())

# 4. 쿠키(Cookies) 우회를 적용한 유튜브 CC 고조회수 영상 다운로드
print("3. 유튜브 CC 영상 다운로드 중 (쿠키 우회 적용)...")

# GitHub Secrets에서 YOUTUBE_COOKIES를 읽어와 임시 cookies.txt 파일 생성
cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
cookie_file_path = None

if cookies_content.strip():
    cookie_file_path = "cookies.txt"
    with open(cookie_file_path, "w", encoding="utf-8") as f:
        f.write(cookies_content)
    print("✓ YOUTUBE_COOKIES 적용 완료!")
else:
    print("⚠️ YOUTUBE_COOKIES가 설정되지 않았습니다. 쿠키 없이 진행합니다.")

ydl_opts = {
    # 'nature 4k relax' 키워드의 CC(재사용 허용) 영상 직접 검색
    'default_search': 'ytsearch1:nature 4k relax creative commons',
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    'outtmpl': 'background.mp4',
    'overwrites': True,
    'quiet': True,
    'cookiefile': cookie_file_path  # 쿠키 전달로 봇 차단 우회
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(["ytsearch1:nature 4k relax creative commons"])
    print("✓ 배경 영상 다운로드 성공!")
finally:
    # 실행 완료 후 임시 쿠키 파일 안전하게 삭제
    if cookie_file_path and os.path.exists(cookie_file_path):
        os.remove(cookie_file_path)

# 5. 영상 + 음성 + 자막 합성
print("4. 쇼츠 영상 합성 중...")
audio = AudioFileClip("voice.mp3")
full_video = VideoFileClip("background.mp4")

# 오디오 길이에 맞춰 배경 영상 구간 추출 (영상 길이가 충분하면 10초 후부터 추출)
start_time = 10 if full_video.duration > (audio.duration + 10) else 0
video = full_video.subclip(start_time, start_time + audio.duration)

# 한글 자막 생성
txt_clip = TextClip(
    script_text, 
    fontsize=35, 
    color='white', 
    bg_color='black', 
    size=(int(video.w * 0.8), None), 
    method='caption', 
    font='NanumGothic'
)
txt_clip = txt_clip.set_position('center').set_duration(audio.duration)

# 최종 오디오/비디오/자막 합성 및 파일 출력
final_video = CompositeVideoClip([video, txt_clip]).set_audio(audio)
final_video.write_videofile("final_shorts.mp4", fps=24, codec='libx264', audio_codec='aac')

print("✨ 유튜브 CC 영상 기반 쇼츠 제작 완료!")
