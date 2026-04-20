# apps/match/services/batch_ingest.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.match.services.igdb_client import IgdbClient
from apps.match.services.igdb_query import build_games_query
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
    def __init__(self, client: IgdbClient | None = None) -> None:
        self.client = client or IgdbClient()

    def run(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        token = self.client.get_access_token()

        all_rows: list[dict[str, Any]] = []
        offset = 0

        for _ in range(self.client.max_pages):
            query = build_games_query(limit=self.client.page_size, offset=offset)
            rows = self.client.fetch_games_page(access_token=token, query=query)
            if not rows:
                break

            all_rows.extend(rows)

            if len(rows) < self.client.page_size:
                break

            offset += self.client.page_size

        passed, reason_counts = filter_games_with_reasons(all_rows)

        stats = IngestStats(
            total_fetched=len(all_rows),
            total_passed=len(passed),
            total_excluded=len(all_rows) - len(passed),
            excluded_reasons=reason_counts,
        )

        return passed, stats.to_dict()
