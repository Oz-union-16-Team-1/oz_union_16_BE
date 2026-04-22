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
    "status",
    "rating",
    "rating_count",
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
    categories = ",".join(map(str, MATCH_INGEST_ALLOWED_CATEGORIES))
    return (
        f"(category = ({categories}))"
        f" & (status = {MATCH_INGEST_REQUIRED_STATUS})"
        f" & (rating_count >= {MATCH_INGEST_MIN_RATING_COUNT})"
        f" & (rating >= {MATCH_INGEST_MIN_RATING})"
        f" & ((aggregated_rating = null) | (aggregated_rating >= {MATCH_INGEST_MIN_AGG_RATING}))"
        f" & (first_release_date >= {MATCH_INGEST_MIN_RELEASE_TS})"
        f" & (platforms = ({MATCH_INGEST_REQUIRED_PLATFORM}))"
        " & (videos != null)"
        " & ((summary != null) | (storyline != null))"
    )

