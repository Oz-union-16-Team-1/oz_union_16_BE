from __future__ import annotations

# UI 단일 선택 장르(1~8) -> IGDB 내부 장르(1~14) 매핑
API_TO_IGDB_GENRE_MAP: dict[int, list[int]] = {
    1: [1, 11],  # 액션/격투
    2: [2, 10],  # 어드벤처/플랫폼
    3: [3, 14],  # RPG/스토리
    4: [5, 6],  # 전략/시뮬
    5: [7, 8],  # 스포츠/레이싱
    6: [9, 12],  # 두뇌/전략
    7: [4],  # 슈팅
    8: [13],  # 음악/리듬
}

# 장르 카드 노출명 (API 응답용)
API_GENRE_NAME_MAP: dict[int, str] = {
    1: "액션/격투",
    2: "어드벤처/플랫폼",
    3: "RPG/스토리",
    4: "전략/시뮬",
    5: "스포츠/레이싱",
    6: "두뇌/전략",
    7: "슈팅",
    8: "음악/리듬",
}

IGDB_GENRE_NAME_MAP: dict[int, str] = {
    1: "액션",
    2: "어드벤처",
    3: "RPG",
    4: "슈팅",
    5: "전략",
    6: "시뮬레이션",
    7: "스포츠",
    8: "레이싱",
    9: "퍼즐",
    10: "플랫폼",
    11: "대전격투",
    12: "카드/보드",
    13: "음악/리듬",
    14: "비주얼노벨",
}

API_TO_IGDB_IMAGE_GENRE_MAP: dict[int, list[int]] = {
    1: [4, 25, 33],  # 액션/격투
    2: [31, 2, 8],  # 어드벤처/플랫폼
    3: [12, 34],  # RPG/스토리
    4: [15, 11, 16, 24, 13],  # 전략/시뮬
    5: [14, 10],  # 스포츠/레이싱
    6: [9, 35, 26, 30],  # 두뇌/전략
    7: [5],  # 슈팅
    8: [7],  # 음악/리듬
}

# 중복 없는 대표 게임 배정을 위한 고정 우선순위
# 후보 수가 적은 장르부터 배정해 충돌(중복 game_id) 가능성을 낮춤
# 음악 -> 스포츠 -> 액션 -> 두뇌 -> 슈팅 -> 전략 -> RPG -> 어드벤처
GENRE_PRIORITY: list[int] = [8, 5, 1, 6, 7, 4, 3, 2]

# 장르 이미지 배치 필터 정책
MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES: tuple[int, ...] = (0, 8, 9)
MATCH_GENRE_IMAGE_REQUIRED_STATUS: int = 0
MATCH_GENRE_IMAGE_REQUIRED_PLATFORM: int = 6  # PC
MATCH_GENRE_IMAGE_MIN_RATING_COUNT: int = 50
MATCH_GENRE_IMAGE_MIN_RATING: float = 70.0

# 조회/완화 범위
MATCH_GENRE_IMAGE_MAX_LOOKBACK_YEARS: int = 10
MATCH_GENRE_IMAGE_MONTHLY_START_DAYS: int = 30
MATCH_GENRE_IMAGE_MONTHLY_END_MONTH: int = 12  # 30일 ~ 12개월
MATCH_GENRE_IMAGE_YEARLY_START: int = 2  # 2년 ~ 10년
MATCH_GENRE_IMAGE_YEARLY_END: int = 10

# 매칭 수집(ingest) 필터 정책
MATCH_INGEST_ALLOWED_CATEGORIES: tuple[int, ...] = (0, 8, 9)  # main/remake/remaster
MATCH_INGEST_REQUIRED_STATUS: int = 0  # released
MATCH_INGEST_REQUIRED_PLATFORM: int = 6  # PC
MATCH_INGEST_MIN_RATING_COUNT: int = 20
MATCH_INGEST_MIN_RATING: float = 50.0
MATCH_INGEST_MIN_AGG_RATING: float = 60.0
MATCH_INGEST_MIN_AGG_RATING_COUNT: int = 3
MATCH_INGEST_MIN_RELEASE_TS: int = 946684800  # 2000-01-01 UTC

# 매칭 후보 선별 상수
MATCH_CANDIDATE_POOL_SIZE: int = 50
MATCH_CANDIDATE_MAX_COUNT: int = 5

# 매칭 응답 제출(POST /match/responses) 상수
MATCH_RESPONSE_MIN_STAR: int = 1
MATCH_RESPONSE_MAX_STAR: int = 5
MATCH_RESPONSE_MIN_ALPHA: float = 0.3
MATCH_RESPONSE_LOW_RATING_LAMBDA: float = 0.15

# 매칭 결과 조회(GET /match/responses/result) 상수
MATCH_RESULT_DEFAULT_PAGE_SIZE: int = 5
MATCH_RESULT_MAX_PAGE_SIZE: int = 15
MATCH_RESULT_MAX_TOTAL_COUNT: int = 15

MATCH_RESULT_SIM_FLOOR: float = 0.20
MATCH_RESULT_TAU_FINAL_STEPS: tuple[float, ...] = (0.35, 0.30, 0.25)

MATCH_RESULT_WEIGHT_SIM: float = 0.75
MATCH_RESULT_WEIGHT_POP: float = 0.15
MATCH_RESULT_WEIGHT_REC: float = 0.10
MATCH_RESULT_WEIGHT_LIKE_BONUS: float = 0.08
MATCH_RESULT_WEIGHT_DISLIKE_PENALTY: float = 0.12
MATCH_RESULT_SCORE_NORMALIZER: float = 1.08  # 0.75+0.15+0.10+0.08

MATCH_RESULT_POP_DEFAULT: float = 0.5
MATCH_RESULT_RECENCY_WINDOW_DAYS: int = 3650  # 10년
MATCH_RESULT_LIKED_TOP_K: int = 5
MATCH_RESULT_LIKED_RATIO_CAP: float = 0.30  # liked 보충 최대 30%

# =========================
# MATCH 벡터 매핑 상수 (14D)
# =========================

MATCH_VECTOR_DIM: int = 14

# 0-based index
MATCH_VECTOR_INDEX: dict[str, int] = {
    "genre_action_fight": 0,  # dim1
    "genre_adventure_platform": 1,  # dim2
    "genre_rpg_story": 2,  # dim3
    "genre_strategy_sim": 3,  # dim4
    "genre_sport_racing": 4,  # dim5
    "genre_brain_puzzle": 5,  # dim6
    "genre_shooter": 6,  # dim7
    "genre_music_rhythm": 7,  # dim8
    "difficulty": 8,  # dim9
    "tone": 9,  # dim10
    "graphics": 10,  # dim11
    "tempo": 11,  # dim12
    "social": 12,  # dim13
    "popularity": 13,  # dim14
}

# 기본값 (태그 없음/값 없음 처리)
MATCH_VECTOR_DEFAULTS: dict[str, float] = {
    "difficulty": 0.0,
    "tone": 0.0,
    "graphics": 0.0,
    "tempo": 0.0,
    "social": 0.0,
    "popularity": 0.5,
}

# 축 집계 규칙
MATCH_VECTOR_AGGREGATION: dict[str, str] = {
    "genre_axis": "max",  # dim1~8
    "mood_axis": "avg",  # dim9~12
    "social_axis": "avg",  # dim13
    "popularity": "direct",  # dim14
}

# 벡터 계산에 쓰는 태그 필드
MATCH_VECTOR_TAG_FIELDS: tuple[str, ...] = (
    "genres",
    "themes",
    "player_perspectives",
    "game_modes",
)

# 기존 장르 매핑 재사용해서 dim(0~7) 자동 생성 (중복 제거)
PGTI_GENRE_TO_VECTOR_DIM: dict[int, int] = {
    igdb_genre_id: api_genre_id - 1
    for api_genre_id, igdb_genre_ids in API_TO_IGDB_GENRE_MAP.items()
    for igdb_genre_id in igdb_genre_ids
}

# dim1~8 (장르축): max 사용
MATCH_VECTOR_GENRE_AXIS_WEIGHTS: dict[str, dict[str, dict[int, float]]] = {
    "genre_action_fight": {
        "genres": {4: 1.0, 25: 0.9},  # Fighting, Hack and Slash
        "themes": {1: 0.7},  # Action
    },
    "genre_adventure_platform": {
        "genres": {8: 1.0, 31: 0.8, 2: 0.5},  # Platform, Adventure, Point-and-Click
    },
    "genre_rpg_story": {
        "genres": {12: 1.0, 34: 0.8, 24: 0.5},  # RPG, Visual Novel, Tactical
        "themes": {31: 0.3},  # Drama
    },
    "genre_strategy_sim": {
        "genres": {11: 1.0, 16: 0.9, 15: 0.8, 13: 0.7, 24: 0.6, 36: 0.5},
        # RTS, TBS, Strategy, Simulator, Tactical, MOBA
    },
    "genre_sport_racing": {
        "genres": {14: 1.0, 10: 1.0},  # Sport, Racing
    },
    "genre_brain_puzzle": {
        "genres": {
            9: 1.0,
            35: 0.9,
            26: 0.8,
            2: 0.5,
        },  # Puzzle, Card/Board, Quiz, Point-and-Click
        "themes": {41: 0.6},  # 4X
    },
    "genre_shooter": {
        "genres": {5: 1.0},  # Shooter
        "themes": {39: 0.4},  # Warfare
    },
    "genre_music_rhythm": {
        "genres": {7: 1.0, 30: 0.3},  # Music, Pinball
    },
}

# dim9~13 (분위기/성향축): avg 사용
MATCH_VECTOR_MOOD_AXIS_WEIGHTS: dict[str, dict[str, dict[int, float]]] = {
    "difficulty": {
        "themes": {
            21: 0.9,
            39: 0.7,
            23: 0.5,
            35: -1.0,
            40: -0.7,
        },  # Survival, Warfare, Stealth, Kids, Party
        "genres": {33: -0.6, 24: 0.8},  # Arcade, Tactical
    },
    "tone": {
        "themes": {
            19: 1.0,
            20: 0.8,
            39: 0.6,
            43: 0.5,
            27: -1.0,
            35: -0.8,
            17: -0.3,
            44: -0.4,
        },
        # Horror, Thriller, Warfare, Mystery, Comedy, Kids, Fantasy, Romance
    },
    "graphics": {
        # IGDB의 Bird view/Isometric은 동일 ID(3)라 단일 가중치로 처리
        "player_perspectives": {1: 1.0, 2: 0.8, 7: 1.0, 4: -1.0, 5: -1.0, 3: -0.4},
        # First person, Third person, VR, Side view, Text, Bird view/Isometric
    },
    "tempo": {
        "genres": {5: 1.0, 4: 1.0, 10: 1.0, 11: 0.8, 16: -1.0, 9: -0.8, 34: -1.0},
        # Shooter, Fighting, Racing, RTS, TBS, Puzzle, Visual Novel
        "themes": {38: 0.5, 21: 0.6},  # Open World, Survival
    },
    "social": {
        "game_modes": {1: -1.0, 2: 1.0, 3: 0.7, 4: 0.5, 6: 0.9},
        # Single player, Multiplayer, Co-operative, Split screen, Battle Royale
    },
}

# dim14 인기도
MATCH_VECTOR_POPULARITY_FIELD: str = "rating"
MATCH_VECTOR_POPULARITY_SCALE: float = 100.0
MATCH_VECTOR_POPULARITY_DEFAULT: float = 0.5

PGTI_GENRE_MATCH_RULES: dict[int, dict[str, tuple[int, ...]]] = {
    1: {"genres": (25, 33), "themes": (1,)},  # 액션
    2: {"genres": (31, 2), "themes": ()},  # 어드벤처
    3: {"genres": (12,), "themes": ()},  # RPG
    4: {"genres": (5,), "themes": ()},  # 슈팅
    5: {"genres": (15, 11, 16, 24, 36), "themes": ()},  # 전략
    6: {"genres": (13,), "themes": ()},  # 시뮬레이션
    7: {"genres": (14,), "themes": ()},  # 스포츠
    8: {"genres": (10,), "themes": ()},  # 레이싱
    9: {"genres": (9, 26, 30), "themes": ()},  # 퍼즐
    10: {"genres": (8,), "themes": ()},  # 플랫폼
    11: {"genres": (4,), "themes": ()},  # 대전격투
    12: {"genres": (35,), "themes": ()},  # 카드/보드
    13: {"genres": (7,), "themes": ()},  # 음악/리듬
    14: {"genres": (34,), "themes": ()},  # 비주얼노벨
}
