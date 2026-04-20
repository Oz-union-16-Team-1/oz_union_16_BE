from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from redis import Redis

from apps.match.constants import API_TO_IGDB_GENRE_MAP
from apps.match.services.genre_image_assignment import GenreImageCandidate, assign_genre_images


class MatchGenreImageBatchService:
    def __init__(self) -> None:
        self.redis = Redis.from_url(
            settings.MATCH_REDIS_URL,
            decode_responses=True,
            socket_timeout=settings.MATCH_GENRE_IMAGE_BATCH_TIMEOUT,
        )
        self.cache_key = settings.MATCH_GENRE_IMAGE_CACHE_KEY

    def _load_previous_map(self) -> dict[int, dict[str, Any]]:
        raw = self.redis.get(self.cache_key)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}

        if not isinstance(data, dict):
            return {}

        normalized: dict[int, dict[str, Any]] = {}
        for k, v in data.items():
            if str(k).isdigit() and isinstance(v, dict):
                normalized[int(k)] = v
        return normalized

    def _fetch_candidates_by_genre(self) -> dict[int, list[GenreImageCandidate]]:
        # IGDB 상세 수집/정렬/파싱은 후속 PR에서 구현
        return {genre_id: [] for genre_id in API_TO_IGDB_GENRE_MAP.keys()}

    def _save_map(self, image_map: dict[int, dict[str, Any]]) -> None:
        # TTL 없이 overwrite
        self.redis.set(self.cache_key, json.dumps(image_map, ensure_ascii=False))

    def run(self) -> dict[str, Any]:
        previous_map = self._load_previous_map()
        candidates_by_genre = self._fetch_candidates_by_genre()

        image_map, stats = assign_genre_images(
            candidates_by_genre=candidates_by_genre,
            previous_map=previous_map,
        )

        self._save_map(image_map)

        return {
            "cache_key": self.cache_key,
            "updated_count": len(image_map),
            "stats": stats,
        }
