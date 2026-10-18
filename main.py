import os
import time
import random
import requests
import asyncio
import edge_tts
from google import genai

# MoviePy v2.0+ 최신 규격 대응
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

# ----------------------------------------------------
# 1. API 키 검증 및 초기화
# ----------------------------------------------------
gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

if not gemini_key:
    raise Exception("❌ GEMINI_API_KEY가 설정되지 않았습니다. Secrets를 확인하세요.")

client = genai.Client(api_key=gemini_key)

# ----------------------------------------------------
# 2. AI 대본 생성 (Gemini 3.8 / 3.5 Flash 지수 대기 재시도)
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
    raise Exception("❌ Gemini API 대본 생성 실패: 모든 백업 모델 요청 거부됨")

print(f"  ✓ 대본 생성 성공: {script_text}")

# ----------------------------------------------------
# 3. 음성 파일 생성 (Edge-TTS)
# ----------------------------------------------------
print("2. 음성 파일 생성 중...")
async def generate_audio():
    communicate = edge_tts.Communicate(script_text, "ko-KR-SunHiNeural")
    await communicate.save("voice.mp3")

asyncio.run(generate_audio())

if not os.path.exists("voice.mp3") or os.path.getsize("voice.mp3") == 0:
    raise Exception("❌ 음성 파일(voice.mp3) 생성 실패")

# ----------------------------------------------------
# 4. Cobalt API 연동 - 유튜브 CC 영상 다운로드 (예외 방어 보강)
# ----------------------------------------------------
print("3. Cobalt API 연동 - 유튜브 인기 CC 영상 안전 다운로드 중...")

# 검증된 인기 유튜브 CC(Creative Commons) 영상 URL Pool
YOUTUBE_CC_URLS = [
    "https://www.youtube.com/watch?v=5fcyVjhL-dc",  # Nature 4K Relax
    "https://www.youtube.com/watch?v=uO-uZ-TiFMQ",  # Space Galaxy 4K
    "https://www.youtube.com/watch?v=my-Bn0oyxKw",  # Deep Ocean Waves
    "https://www.youtube.com/watch?v=LXb3EKWsInQ",  # Forest Aerial 4K
    "https://www.youtube.com/watch?v=2OEL4P1Rz04"   # Northern Lights 4K
]

# Cobalt 퍼블릭 노드 리스트 (예비 백업 인스턴스 포함)
COBALT_INSTANCES = [
    "https://api.cobalt.tools",
    "https://cobalt-api.kwi.sh",
    "https://co.wuk.sh"
]

download_success = False

# 무작위 순서로 노드 및 비디오 순회시도
random.shuffle(YOUTUBE_CC_URLS)

for target_youtube_url in YOUTUBE_CC_URLS:
    if download_success:
        break
        
    print(f"  [타겟 시도] {target_youtube_url}")
    
    for instance in COBALT_INSTANCES:
        try:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            payload = {
                "url": target_youtube_url,
                "videoQuality": "720",  # 안정적인 다운로드를 위해 720p/1080p 지원
                "downloadMode": "auto"
            }
            
            # 1) Cobalt API 스트림 URL 생성 요청
            res = requests.post(f"{instance}/", json=payload, headers=headers, timeout=12)
            
            # Non-JSON response 방어
            if res.status_code != 200:
                print(f"  ⚠️ 노드({instance}) 상태코드 비정상: {res.status_code}")
                continue
                
            try:
                data = res.json()
            except Exception:
                print(f"  ⚠️ 노드({instance})에서 비정상 응답(Non-JSON) 반환")
                continue
                
            stream_url = data.get("url")
            
            # 2) 스트림 URL 다운로드 시도
            if stream_url:
                print(f"  ✓ 직링크 확보 성공! ({instance}) 다운로드 진행...")
                video_res = requests.get(stream_url, headers=headers, timeout=35, stream=True)
                
                if video_res.status_code == 200:
                    with open("background.mp4", "wb") as f:
                        for chunk in video_res.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                                
                    if os.path.exists("background.mp4") and os.path.getsize("background.mp4") > 1000000: # 최소 1MB 이상 확인
                        download_success = True
                        print("  ✓ 유튜브 CC 영상 완벽 다운로드 성공!")
                        break
                    else:
                        print("  ⚠️ 다운로드된 영상 파일이 손상되었거나 용량이 너무 작습니다.")
            else:
                print(f"  ⚠️ 스트림 URL 추출 실패 ({instance}): {data.get('text', '알 수 없는 오류')}")
                
        except requests.exceptions.Timeout:
            print(f"  ⚠️ 노드 타임아웃 발생 ({instance})")
            continue
        except Exception as e:
            print(f"  ⚠️ 노드 예외 발생 ({instance}): {e}")
            continue

if not download_success:
    raise Exception("❌ 유튜브 우회 다운로드 실패: 모든 Cobalt 노드 및 영상 URL 추출 불가능")

# ----------------------------------------------------
# 5. 영상 + 음성 + 자막 합성 (MoviePy v2.0+ 안전 처리)
# ----------------------------------------------------
print("4. 쇼츠 영상 합성 중...")

audio = None
full_video = None
video = None
final_video = None

try:
    audio = AudioFileClip("voice.mp3")
    full_video = VideoFileClip("background.mp4")

    # 구간 다듬기 (동영상 길이가 오디오보다 짧은 경우 예외 방어)
    if full_video.duration <= audio.duration:
        start_time = 0
        target_duration = full_video.duration
    else:
        start_time = 2 if full_video.duration > (audio.duration + 2) else 0
        target_duration = audio.duration

    if hasattr(full_video, "subclipped"):
        video = full_video.subclipped(start_time, start_time + target_duration)
    else:
        video = full_video.subclip(start_time, start_time + target_duration)

    # 폰트 경로 및 캡션 설정
    font_path = '/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
    font_name = font_path if os.path.exists(font_path) else 'NanumGothic'

    txt_clip = TextClip(
        text=script_text, 
        font_size=35, 
        color='white', 
        bg_color='black', 
        size=(int(video.w * 0.8), None), 
        method='caption', 
        font=font_name
    )

    if hasattr(txt_clip, "with_position"):
        txt_clip = txt_clip.with_position('center').with_duration(target_duration)
    else:
        txt_clip = txt_clip.set_position('center').set_duration(target_duration)

    final_video = CompositeVideoClip([video, txt_clip])

    if hasattr(final_video, "with_audio"):
        final_video = final_video.with_audio(audio)
    else:
        final_video = final_video.set_audio(audio)

    # 렌더링
    final_video.write_videofile("final_shorts.mp4", fps=24, codec='libx264', audio_codec='aac')
    print("✨ [성공] final_shorts.mp4 제작이 완료되었습니다!")

finally:
    # 예외 발생 시에도 시스템 자원(파일 락)을 확실히 해제하도록 구현
    if audio: audio.close()
    if full_video: full_video.close()
    if video: video.close()
    if final_video: final_video.close()
