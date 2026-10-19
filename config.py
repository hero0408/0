import os

# API 키 세팅
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "YOUR_MINIMAX_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "YOUR_PIXABAY_API_KEY")

# 출력 및 에셋 경로
OUTPUT_DIR = "outputs"
ASSETS_DIR = "assets"
BGM_PATH = os.path.join(ASSETS_DIR, "audio", "music_box_theme.mp3")

# 영상 규격 설정
VIDEO_FPS = 24
VIDEO_PRESET = "medium"
VIDEO_THREADS = 4
