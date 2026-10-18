import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. GitHub Secrets에서 인증 토큰 불러오기
CLIENT_ID = os.environ["YOUTUBE_CLIENT_ID"]
CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]

# 2. 인증 객체 생성
creds = Credentials(
    token=None,
    refresh_token=REFRESH_TOKEN,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    scopes=['https://www.googleapis.com/auth/youtube.upload']
)

youtube = build('youtube', 'v3', credentials=creds)

# 3. 업로드할 동영상 정보 설정
body = {
    'snippet': {
        'title': '매일 배우는 15초 재미있는 상식 #Shorts',
        'description': '오늘의 흥미로운 상식입니다. #Shorts #상식 #AI',
        'tags': ['Shorts', '상식', '지식', 'AI'],
        'categoryId': '27' # 교육(Education) 카테고리
    },
    'status': {
        'privacyStatus': 'public', # 공개 상태 (public / private / unlisted)
        'selfDeclaredMadeForKids': False
    }
}

# 4. 파일 세팅 및 업로드 실행
file_path = "final_shorts.mp4"
media = MediaFileUpload(file_path, chunksize=-1, resumable=True, mimetype='video/mp4')

print("유튜브 업로드 시작...")
request = youtube.videos().insert(
    part=','.join(body.keys()),
    body=body,
    media_body=media
)

response = None
while response is None:
    status, response = request.next_chunk()
    if status:
        print(f"업로드 진행률: {int(status.progress() * 100)}%")

print(f"✨ 업로드 완료! 동영상 ID: {response['id']}")
