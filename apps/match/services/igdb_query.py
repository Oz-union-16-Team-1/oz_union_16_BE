from __future__ import annotations

from apps.match.constants import (
    MATCH_INGEST_ALLOWED_CATEGORIES,
    MATCH_INGEST_MIN_AGG_RATING,
    MATCH_INGEST_MIN_RATING,
    MATCH_INGEST_MIN_RATING_COUNT,
    MATCH_INGEST_MIN_RELEASE_TS,
    MATCH_INGEST_REQUIRED_PLATFORM,
    MATCH_INGEST_REQUIRED_STATUS,
)

IGDB_GAME_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "category",
    "game_type",
    "status",
    "rating",
    "rating_count",
    "total_rating",
    "total_rating_count",
    "aggregated_rating",
    "first_release_date",
    "genres",
    "themes",
    "game_modes",
    "player_perspectives",
    "platforms",
    "videos",
    "summary",
    "storyline",
    "updated_at",
)

IGDB_GAMES_SORT_CLAUSE = "id asc"


def get_games_field_clause() -> str:
    return ",".join(IGDB_GAME_FIELDS)


def build_games_where_clause() -> str:
    # IGDB where는 안정적인 숫자/배열 필드 중심으로 최소화
    # 나머지 상세 검증(category/status/videos/description/aggregated)은 ingest_filters에서 처리
    min_rating = f"{MATCH_INGEST_MIN_RATING:g}"  # "50"
    return (
        f"(rating_count >= {MATCH_INGEST_MIN_RATING_COUNT})"
        f" & (rating >= {min_rating})"
        f" & (first_release_date >= {MATCH_INGEST_MIN_RELEASE_TS})"
        f" & (platforms = ({MATCH_INGEST_REQUIRED_PLATFORM}))"
    )
