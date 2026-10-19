import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Config:
    # API Keys & Credentials
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    YOUTUBE_CLIENT_ID: str = os.environ.get("YOUTUBE_CLIENT_ID", "")
    YOUTUBE_CLIENT_SECRET: str = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    YOUTUBE_REFRESH_TOKEN: str = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

    # Video Settings
    VIDEO_WIDTH: int = 1080
    VIDEO_HEIGHT: int = 1920
    FPS: int = 24
    
    # File Paths
    OPENING_PATH: str = "opening.mp4"
    CLOSING_PATH: str = "closing.mp4"
    BASE_VIDEO_PATH: str = "base_render.mp4"
    OUTPUT_VIDEO_PATH: str = "output_ko.mp4"
    METADATA_PATH: str = "metadata.json"

    # Edge-TTS Voice Mapping (한국어 전용 기준)
    VOICE_MAP = {
        'Ein': 'ko-KR-InJoonNeural',     # 아인 (은여우 - 스마트/영민함)
        'Chrono': 'ko-KR-BongJinNeural', # 크로노 (호랑이 - 중저음/엄격함)
        'Escape': 'ko-KR-SunHiNeural'    # 이스케이프 (토끼 - 경쾌/빠름)
    }

config = Config()
