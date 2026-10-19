# ============================================================
# [Clockwork Repository] 3D Animation Pipeline Prompt System
# ============================================================

# 1. 고화질 3D 렌더링 & 모션 연출 마스터 프롬프트
MASTER_STYLE_3D = (
    "High quality 3D Pixar animated film style, soft volumetric warm studio lighting, "
    "highly detailed soft fur texture, smooth character movement, natural body animation, "
    "fluid camera transition, cinematic pan, 9:16 vertical ratio -- "
)

# 2. 캐릭터 기본 디자인 프롬프트
CHARACTER_BASE_PROMPTS = {
    "AIN": (
        "An adorable fluffy silver baby fox named Ain, expressive big sparkling blue eyes, "
        "wearing a detailed leather harness with a giant polished brass clockwork key on its back"
    ),
    "CHRONO": (
        "A cute fluffy baby tiger named Chrono, warm friendly eyes, "
        "wearing a small leather utility tool belt with tiny brass wrenches"
    ),
    "GOVERNOR_IRON_PENDULUM": (
        "A massive menacing brass clockwork governor named Iron Pendulum, "
        "wearing a majestic imperial mantle, glowing purple core on chest"
    )
}

# 3. 트릴로지 메타데이터
TRILOGY_METADATA = {
    1: {
        "title": "시침이 멈춘 시간 보관소",
        "theme": "은밀한 반전 스릴러 & 다정한 이웃의 위장",
        "location": "앤틱 시계탑 보관소 내부, 거대 놋쇠 톱니바퀴 공간",
        "climax": "에스케이프의 폭로('너는 보관소에 봉인된 거야!')와 천장이 열리며 하늘 위 제국 유출"
    },
    2: {
        "title": "시계 제국 크로노폴리스",
        "theme": "거대 스팀펑크 대도시 로드무비 & 흑막 총독과의 대립",
        "location": "공중 톱니바퀴 대도시 '크로노폴리스' 전경",
        "climax": "아인 등 뒤의 태엽 키가 황실의 전설적 시간 동력원임을 확인"
    },
    3: {
        "title": "시공간의 수호자",
        "theme": "진짜 기억 되찾기, 제국 함선 침투, 세계의 시간 해방",
        "location": "제국 총독 함선 내부 및 시공간의 틈새",
        "climax": "아인의 각성과 시간 정화, 새로운 시공간 수호자로의 거듭남"
    }
}

# 4. 에스케이프(Escape) 동적 상태 관리
def get_escape_prompt(season: int, episode: int) -> str:
    if season == 1:
        if episode <= 6:
            return (
                "An extremely innocent fluffy white baby rabbit named Escape, big sparkling pink eyes, "
                "holding a tiny golden broom, warm friendly smile"
            )
        elif episode <= 11:
            return (
                "A cute fluffy white baby rabbit named Escape, acting sweet but with subtle mysterious pink eyes, "
                "holding an antique brass hourglass necklace"
            )
        else:
            return (
                "A sneaky clever white baby rabbit named Escape, wearing a glowing brass hourglass necklace, "
                "villainous smirk, intense glare"
            )
    elif season == 2:
        return "An agile sneaky white rabbit named Escape, wearing a leather watch strap, competitive glare"
    else:
        return "A refined white rabbit named Escape, holding a miniature repair wrench, apologetic subtle smile"

# 5. Gemini 대본 생성용 시스템 프롬프트 조립
def build_system_prompt_for_script(season: int, episode: int) -> str:
    season_data = TRILOGY_METADATA.get(season, TRILOGY_METADATA[1])
    escape_prompt = get_escape_prompt(season, episode)

    return f"""
    당신은 3D 애니메이션 '시침이 멈춘 시간 보관소' 트릴로지의 수석 작가입니다.
    현재 작성할 영상은 [시즌 {season}: {season_data['title']}]의 {episode}화(5분 분량, 총 15개 씬)입니다.

    [세계관 및 회차 정보]
    - 시즌 주제: {season_data['theme']}
    - 공간 배경: {season_data['location']}
    - 시즌 클라이맥스 방향성: {season_data['climax']}

    [등장인물 프롬프트 정보]
    - 아인(Hero): {CHARACTER_BASE_PROMPTS['AIN']}
    - 크로노(Sidekick): {CHARACTER_BASE_PROMPTS['CHRONO']}
    - 에스케이프(Antagonist): {escape_prompt}

    [시퀀스 연출 가이드라인]
    1. 캐릭터 간 동선과 카메라 커팅이 자연스럽도록 video_prompt를 구체적으로 작성하세요.
    2. 시즌 1에서는 에스케이프가 직접적인 악행을 드러내지 않게 하고, 씬 마지막에 아인의 '태엽 키'를 노리는 복선 시선을 배치하세요.
    3. 프롬프트 끝에는 반드시 'MASTER_STYLE_3D' 수식어가 포함되도록 반영하세요.

    [응답 포맷 (반드시 순수 JSON 형식만 출력)]
    {{
        "season": {season},
        "episode": {episode},
        "title": "에피소드 제목",
        "scenes": [
            {{
                "scene_id": 1,
                "narration": "한국어 나레이션 문구",
                "video_prompt": "영문 비디오 프롬프트 + {MASTER_STYLE_3D}",
                "duration": 10
            }}
        ]
    }}
    """
