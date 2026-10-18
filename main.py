import os
import requests
import asyncio
import edge_tts
import yt_dlp
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# 1. API 키 및 클라이언트 설정
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

YOUTUBE_CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
YOUTUBE_REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

# 2. AI 대본 생성 (gemini-3.8-flash 사용)
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

# 4. 유튜브 CC(재사용 허용) 최신 인기 영상 검색 및 다운로드
print("3. 유튜브에서 재사용 가능한(CC) 최신 영상 검색 중...")

creds = Credentials(
    token=None,
    refresh_token=YOUTUBE_REFRESH_TOKEN,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=YOUTUBE_CLIENT_ID,
    client_secret=YOUTUBE_CLIENT_SECRET
)
youtube_api = build('youtube', 'v3', credentials=creds)

# CC 라이선스(videoLicense='creativeCommon') 및 조회수 높은 영상 검색
search_response = youtube_api.search().list(
    q='nature 4k relax',
    part='id,snippet',
    maxResults=5,
    type='video',
    videoLicense='creativeCommon',
    order='viewCount'
).execute()

video_id = search_response['items'][0]['id']['videoId']
youtube_url = f"https://www.youtube.com/watch?v={video_id}"
print(f"선택된 CC 영상 URL: {youtube_url}")

# yt-dlp로 배경 영상 다운로드
ydl_opts = {
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    'outtmpl': 'background.mp4',
    'overwrites': True
}
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([youtube_url])

# 5. 영상 + 음성 + 자막 합성
print("4. 쇼츠 영상 합성 중...")
audio = AudioFileClip("voice.mp3")

# 영상의 앞부분 10초 이후 구간에서 음성 길이만큼 추출
full_video = VideoFileClip("background.mp4")
start_time = 10 if full_video.duration > 20 else 0
video = full_video.subclip(start_time, start_time + audio.duration)

# 자막 생성
txt_clip = TextClip(script_text, fontsize=35, color='white', bg_color='black', 
                    size=(int(video.w * 0.8), None), method='caption', font='NanumGothic')
txt_clip = txt_clip.set_position('center').set_duration(audio.duration)

# 최종 합성 및 저장
final_video = CompositeVideoClip([video, txt_clip]).set_audio(audio)
final_video.write_videofile("final_shorts.mp4", fps=24, codec='libx264', audio_codec='aac')
print("✨ 유튜브 CC 영상 기반 쇼츠 제작 완료!")
