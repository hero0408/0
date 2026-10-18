import os
import requests
import asyncio
import edge_tts
import yt_dlp
from google import genai
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# 1. Gemini API 설정
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

# 4. yt-dlp를 이용한 유튜브 4K CC 영상 검색 및 다운로드
print("3. 유튜브에서 재사용 가능한(CC) 4K 배경 영상 다운로드 중...")
ydl_opts = {
    # 유튜브에서 'nature 4k relax' 키워드로 CC 라이선스 영상 직접 검색 다운로드
    'default_search': 'ytsearch1:nature 4k relax creative commons',
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    'outtmpl': 'background.mp4',
    'overwrites': True,
    'quiet': True
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download(["ytsearch1:nature 4k relax creative commons"])

# 5. 영상 + 음성 + 자막 합성
print("4. 쇼츠 영상 합성 중...")
audio = AudioFileClip("voice.mp3")

# 영상 구간 추출
full_video = VideoFileClip("background.mp4")
start_time = 10 if full_video.duration > 20 else 0
video = full_video.subclip(start_time, start_time + audio.duration)

# 자막 합성
txt_clip = TextClip(script_text, fontsize=35, color='white', bg_color='black', 
                    size=(int(video.w * 0.8), None), method='caption', font='NanumGothic')
txt_clip = txt_clip.set_position('center').set_duration(audio.duration)

final_video = CompositeVideoClip([video, txt_clip]).set_audio(audio)
final_video.write_videofile("final_shorts.mp4", fps=24, codec='libx264', audio_codec='aac')
print("✨ 유튜브 CC 영상 기반 쇼츠 제작 완료!")
