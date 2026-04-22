from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.core import igdb_client
from apps.match.services.igdb_query import (
    IGDB_GAMES_SORT_CLAUSE,
    build_games_where_clause,
    get_games_field_clause,
)
from apps.match.services.ingest_filters import filter_games_with_reasons


@dataclass
class IngestStats:
    total_fetched: int = 0
    total_passed: int = 0
    total_excluded: int = 0
    excluded_reasons: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_fetched": self.total_fetched,
            "total_passed": self.total_passed,
            "total_excluded": self.total_excluded,
            "excluded_reasons": self.excluded_reasons or {},
        }


class MatchBatchIngestService:
    def __init__(
        self,
        page_size: int | None = None,
        max_pages: int | None = None,
        request_interval: float | None = None,
    ) -> None:
        self.page_size = page_size or settings.IGDB_PAGE_SIZE
        self.max_pages = max_pages or settings.IGDB_MAX_PAGES
        self.request_interval = (
            request_interval
            if request_interval is not None
            else settings.IGDB_REQUEST_INTERVAL
        )

    def run(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        # 수집/필터/집계까지만 수행 (DB 업서트/Redis 적재는 후속 PR)
        all_rows: list[dict[str, Any]] = []
        offset = 0

        fields_clause = get_games_field_clause()
        where_clause = build_games_where_clause()

        for _ in range(self.max_pages):
            rows = igdb_client.query_games(
                fields=fields_clause,
                where=where_clause,
                sort=IGDB_GAMES_SORT_CLAUSE,
                limit=self.page_size,
                offset=offset,
            )

            if not rows:
                break
            if not isinstance(rows, list):
                break

            all_rows.extend(rows)

            if len(rows) < self.page_size:
                break

            offset += self.page_size
            if self.request_interval > 0:
                time.sleep(self.request_interval)

        passed, reason_counts = filter_games_with_reasons(all_rows)

        stats = IngestStats(
            total_fetched=len(all_rows),
            total_passed=len(passed),
            total_excluded=len(all_rows) - len(passed),
            excluded_reasons=reason_counts,
        )

        return passed, stats.to_dict()
