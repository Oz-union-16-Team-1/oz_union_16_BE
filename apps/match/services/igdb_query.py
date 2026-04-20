from __future__ import annotations

from django.conf import settings

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


def get_games_field_clause() -> str:
    return ",".join(IGDB_GAME_FIELDS)


def build_games_query(*, limit: int, offset: int) -> str:
    where_clause = (
        "where "
        "(category = (0,8,9))"
        " & (status = 0)"
        f" & (rating_count >= {settings.MATCH_FILTER_MIN_RATING_COUNT})"
        f" & (rating >= {settings.MATCH_FILTER_MIN_RATING})"
        f" & ((aggregated_rating = null) | (aggregated_rating >= {settings.MATCH_FILTER_MIN_AGG_RATING}))"
        f" & (first_release_date >= {settings.MATCH_FILTER_MIN_RELEASE_TS})"
        " & (platforms = (6))"
        " & (videos != null)"
        " & ((summary != null) | (storyline != null));"
    )

    return "\n".join(
        [
            f"fields {get_games_field_clause()};",
            where_clause,
            "sort id asc;",
            f"limit {limit};",
            f"offset {offset};",
        ]
    )
