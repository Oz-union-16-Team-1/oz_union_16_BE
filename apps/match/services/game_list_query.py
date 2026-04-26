from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.games.models import Game

INGEST_DB_FIELDS: tuple[str, ...] = (
    "game_id",
    "name",
    "category",
    "game_type",
    "status",
    "rating",
    "rating_count",
    "total_rating",
    "total_rating_count",
    "aggregated_rating",
    "aggregated_rating_count",
    "first_release_date",
    "genres",
    "themes",
    "game_modes",
    "player_perspectives",
    "videos",
    "summary",
    "storyline",
)


def _to_unix_timestamp(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())


def to_ingest_row(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    row["id"] = row.get("game_id")
    row["first_release_date"] = _to_unix_timestamp(row.get("first_release_date"))
    return row


def fetch_ingest_rows_from_game_list(
    page_size: int,
    max_pages: int,
) -> list[dict[str, Any]]:
    queryset = (
        Game.objects.filter(is_ban=False).order_by("game_id").values(*INGEST_DB_FIELDS)
    )

    rows: list[dict[str, Any]] = []
    offset = 0

    for _ in range(max_pages):
        chunk = list(queryset[offset : offset + page_size])
        if not chunk:
            break

        for item in chunk:
            rows.append(to_ingest_row(item))

        if len(chunk) < page_size:
            break

        offset += page_size

    return rows
