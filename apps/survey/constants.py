SURVEY_RECOMMENDATION_DEFAULT_PAGE_SIZE = 5
SURVEY_RECOMMENDATION_MAX_PAGE_SIZE = 15
SURVEY_RECOMMENDATION_REQUIRED_PLATFORM_ID = 6
SURVEY_RECOMMENDATION_MIN_RELEASE_YEAR = 2000

SURVEY_ALLOWED_GAME_CATEGORIES: tuple[int, ...] = (0, 8, 9)
SURVEY_REQUIRED_RELEASE_STATUS: int = 0

SURVEY_GENRE_NAME_MAP: dict[int, str] = {
    2: "포인트앤클릭",
    4: "대전격투",
    5: "슈팅",
    7: "음악",
    8: "플랫폼",
    9: "퍼즐",
    10: "레이싱",
    11: "전략",
    12: "RPG",
    13: "시뮬레이션",
    14: "스포츠",
    15: "전략",
    16: "턴제전략",
    24: "택티컬",
    25: "핵앤슬래시",
    26: "퀴즈",
    30: "핀볼",
    31: "어드벤처",
    33: "아케이드",
    34: "비주얼노벨",
    35: "카드/보드",
    36: "MOBA",
}
