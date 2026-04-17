from __future__ import annotations

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
    return "\n".join(
        [
            f"fields {get_games_field_clause()};",
            "sort id asc;",
            f"limit {limit};",
            f"offset {offset};",
        ]
    )
