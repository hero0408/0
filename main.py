import os
import requests
import asyncio
import edge_tts
import google.generativeai as genai
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# 1. API 키 설정 (GitHub Secrets에서 불러옴)
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
PIXABAY_API_KEY = os.environ["PIXABAY_API_KEY"]

# 2. AI 대본 생성 (Gemini)
print("1. AI 대본 생성 중...")
model = genai.GenerativeModel('gemini-1.5-flash')
prompt = "유튜브 쇼츠용 흥미로운 상식 1가지를 15초 분량(한국어 3~4문장)으로 작성해줘. 응답은 오직 대본 내용만 출력해."
response = model.generate_content(prompt)
script_text = response.text.strip()
print(f"대본: {script_text}")

# 3. 음성 파일 생성 (Edge-TTS)
print("2. 음성 파일(TTS) 생성 중...")
async def generate_audio():
    # 한국어 여성 아나운서 음성
    communicate = edge_tts.Communicate(script_text, "ko-KR-SunHiNeural")
    await communicate.save("voice.mp3")

asyncio.run(generate_audio())

# 4. 배경 영상 다운로드 (Pixabay API)
print("3. Pixabay에서 배경 영상 다운로드 중...")
pixabay_url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q=nature&video_type=film&per_page=5"
res = requests.get(pixabay_url).json()

# 검색된 첫 번째 비디오 파일 다운로드
video_info = res['hits'][0]['videos']
video_download_url = video_info['medium']['url']

with open("background.mp4", "wb") as f:
    f.write(requests.get(video_download_url).content)

# 5. 영상 + 음성 + 자막 합성 (MoviePy)
print("4. 쇼츠 영상 합성 중...")
audio = AudioFileClip("voice.mp3")
video = VideoFileClip("background.mp4").subclip(0, audio.duration) # 음성 길이에 맞춤

# 자막 생성 (화면 중앙 위치)
txt_clip = TextClip(script_text, fontsize=40, color='white', bg_color='black', 
                    size=(video.w * 0.8, None), method='caption')
txt_clip = txt_clip.set_position('center').set_duration(audio.duration)

# 최종 합성
final_video = CompositeVideoClip([video, txt_clip]).set_audio(audio)
final_video.write_videofile("final_shorts.mp4", fps=24, codec='libx264', audio_codec='aac')

print("✨ 영상 제작 완료: final_shorts.mp4")
