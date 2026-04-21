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

API_TO_IGDB_IMAGE_GENRE_MAP: dict[int, list[int]] = {
    1: [4, 25, 33],          # 액션/격투
    2: [31, 2, 8],           # 어드벤처/플랫폼
    3: [12, 34],             # RPG/스토리
    4: [15, 11, 16, 24, 13], # 전략/시뮬
    5: [14, 10],             # 스포츠/레이싱
    6: [9, 35, 26, 30],      # 두뇌/전략
    7: [5],                  # 슈팅
    8: [7],                  # 음악/리듬
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
MATCH_GENRE_IMAGE_MONTHLY_END_MONTH: int = 12   # 30일 ~ 12개월
MATCH_GENRE_IMAGE_YEARLY_START: int = 2          # 2년 ~ 10년
MATCH_GENRE_IMAGE_YEARLY_END: int = 10
