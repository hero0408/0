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

# 4. 유튜브 CC 영상 다운로드 (포맷 우회 완결판)
print("3. 유튜브 CC 영상 다운로드 중...")

cookies_content = os.environ.get("YOUTUBE_COOKIES", "")
cookie_file_path = None

if cookies_content.strip():
    cookie_file_path = "cookies.txt"
    with open(cookie_file_path, "w", encoding="utf-8") as f:
        f.write(cookies_content)
    print("✓ YOUTUBE_COOKIES 적용 완료!")

ydl_opts = {
    'default_search': 'ytsearch1:nature 4k relax creative commons',
    # 💡 무조건 다운로드 가능한 최상위 포맷을 가져오도록 설정
    'format': 'best',
    'outtmpl': 'background.mp4',
    'overwrites': True,
    'quiet': True,
    'cookiefile': cookie_file_path if cookie_file_path else None,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios', 'web'],
            'skip': ['hls', 'dash']
        }
    }
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download(["ytsearch1:nature 4k relax creative commons"])
    print("✓ 배경 영상 다운로드 성공!")
finally:
    if cookie_file_path and os.path.exists(cookie_file_path):
        os.remove(cookie_file_path)

# 5. 영상 + 음성 + 자막 합성
print("4. 쇼츠 영상 합성 중...")
audio = AudioFileClip("voice.mp3")
full_video = VideoFileClip("background.mp4")

start_time = 10 if full_video.duration > (audio.duration + 10) else 0
video = full_video.subclip(start_time, start_time + audio.duration)

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

final_video = CompositeVideoClip([video, txt_clip]).set_audio(audio)
final_video.write_videofile("final_shorts.mp4", fps=24, codec='libx264', audio_codec='aac')

print("✨ 유튜브 CC 영상 기반 쇼츠 제작 완료!")
