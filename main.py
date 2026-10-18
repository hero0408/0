import os
import requests
import asyncio
import edge_tts
from google import genai
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# 1. API 키 설정 (GEMINI_API_KEY 또는 GOOGLE_API_KEY 인식)
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)
PIXABAY_API_KEY = os.environ["PIXABAY_API_KEY"]

# 2. AI 대본 생성 (최신 gemini-2.5-flash 모델 적용)
print("1. AI 대본 생성 중...")
prompt = "유튜브 쇼츠용 흥미로운 상식 1가지를 15초 분량(한국어 3~4문장)으로 작성해줘. 응답은 오직 대본 내용만 출력해."
response = client.models.generate_content(
    model='gemini-2.5-flash',
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

# 4. 배경 영상 다운로드 (Pixabay API)
print("3. Pixabay에서 배경 영상 다운로드 중...")
pixabay_url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q=nature&video_type=film&per_page=5"
res = requests.get(pixabay_url).json()

video_info = res['hits'][0]['videos']
video_download_url = video_info['medium']['url']

with open("background.mp4", "wb") as f:
    f.write(requests.get(video_download_url).content)

# 5. 영상 + 음성 + 자막 합성
print("4. 쇼츠 영상 합성 중...")
audio = AudioFileClip("voice.mp3")
video = VideoFileClip("background.mp4").subclip(0, audio.duration)

txt_clip = TextClip(script_text, fontsize=35, color='white', bg_color='black', 
                    size=(int(video.w * 0.8), None), method='caption', font='NanumGothic')
txt_clip = txt_clip.set_position('center').set_duration(audio.duration)

final_video = CompositeVideoClip([video, txt_clip]).set_audio(audio)
final_video.write_videofile("final_shorts.mp4", fps=24, codec='libx264', audio_codec='aac')
print("✨ 영상 제작 완료!")
