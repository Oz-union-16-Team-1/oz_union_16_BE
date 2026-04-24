from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings

from apps.match.services.game_list_query import fetch_ingest_rows_from_game_list
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


class MatchCandidateFilterBatchService:
    def __init__(
        self,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> None:
        self.page_size = page_size or settings.IGDB_PAGE_SIZE
        self.max_pages = max_pages or settings.IGDB_MAX_PAGES

    def run(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        # game_list 조회 결과를 필터링하고 통계를 집계한다.
        all_rows = fetch_ingest_rows_from_game_list(
            page_size=self.page_size,
            max_pages=self.max_pages,
        )

        passed, reason_counts = filter_games_with_reasons(all_rows)

        stats = IngestStats(
            total_fetched=len(all_rows),
            total_passed=len(passed),
            total_excluded=len(all_rows) - len(passed),
            excluded_reasons=reason_counts,
        )

        return passed, stats.to_dict()
