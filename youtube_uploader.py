import os
import json
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YouTubeUploader")

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def get_authenticated_service():
    if not all([config.YOUTUBE_CLIENT_ID, config.YOUTUBE_CLIENT_SECRET, config.YOUTUBE_REFRESH_TOKEN]):
        raise ValueError("YouTube OAuth 인증을 위한 환경 변수(YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN)가 부족합니다.")

    credentials = Credentials(
        token=None,
        refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.YOUTUBE_CLIENT_ID,
        client_secret=config.YOUTUBE_CLIENT_SECRET,
        scopes=SCOPES
    )
    return build('youtube', 'v3', credentials=credentials)

def upload_private_video(video_file_path: str = config.OUTPUT_VIDEO_PATH) -> str:
    youtube = get_authenticated_service()
    
    title = "The Clockwork Time Repository"
    if os.path.exists(config.METADATA_PATH):
        with open(config.METADATA_PATH, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            title = metadata.get("title_ko", title)

    if not os.path.exists(video_file_path):
        logger.error(f"업로드할 비디오 파일이 없습니다: {video_file_path}")
        return ""

    body = {
        'snippet': {
            'title': f"[시계태엽 시간 보관소] {title}",
            'description': "The Clockwork Time Repository - Automated Pipeline Generation",
            'tags': ['시계태엽시간보관소', 'ClockworkTimeRepository', '3DAnimation', 'Shorts'],
            'categoryId': '1'  # Film & Animation
        },
        'status': {
            'privacyStatus': 'private',  # 자동 비공개 업로드
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload(video_file_path, chunksize=-1, resumable=True, mimetype='video/mp4')
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)

    logger.info(f"YouTube 비공개 업로드 진행 중: {video_file_path}")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"업로드 진행률: {int(status.progress() * 100)}%")

    video_id = response.get('id', '')
    logger.info(f"유튜브 비공개 업로드 완료! Video ID: {video_id}")
    return video_id

if __name__ == "__main__":
    upload_private_video()
