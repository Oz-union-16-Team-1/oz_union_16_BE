from __future__ import annotations

import json
import time
from typing import Any

from django.conf import settings
from redis import Redis

from apps.core import igdb_client
from apps.match.constants import (
    API_TO_IGDB_GENRE_MAP,
    MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES,
    MATCH_GENRE_IMAGE_MAX_LOOKBACK_YEARS,
    MATCH_GENRE_IMAGE_MIN_RATING,
    MATCH_GENRE_IMAGE_MIN_RATING_COUNT,
    MATCH_GENRE_IMAGE_REQUIRED_PLATFORM,
    MATCH_GENRE_IMAGE_REQUIRED_STATUS,
)
from apps.match.services.genre_image_assignment import (
    GenreImageCandidate,
    assign_genre_images,
)


def _normalize_cover_url(url: Any) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    normalized = f"https:{url}" if url.startswith("//") else url
    return normalized.replace("t_thumb", "t_1080p")


class MatchGenreImageBatchService:
    def __init__(self) -> None:
        self.redis = Redis.from_url(
            settings.MATCH_REDIS_URL,
            decode_responses=True,
            socket_timeout=settings.MATCH_GENRE_IMAGE_BATCH_TIMEOUT,
        )
        self.cache_key = settings.MATCH_GENRE_IMAGE_CACHE_KEY

    def _fetch_candidates_by_genre(self) -> dict[int, list[GenreImageCandidate]]:
        # 현재 시점 기준 최대 조회 범위(10년) 하한 타임스탬프
        lookback_ts = int(time.time()) - (
                MATCH_GENRE_IMAGE_MAX_LOOKBACK_YEARS * 365 * 24 * 60 * 60
        )
        out: dict[int, list[GenreImageCandidate]] = {}

        for api_genre_id, igdb_genre_ids in API_TO_IGDB_GENRE_MAP.items():
            genre_str = ",".join(map(str, igdb_genre_ids))
            where = (
                f"genres = ({genre_str})"
                f" & first_release_date >= {lookback_ts}"
                f" & total_rating != null"
                f" & total_rating_count >= {MATCH_GENRE_IMAGE_MIN_RATING_COUNT}"
                f" & cover != null"
                f" & status = {MATCH_GENRE_IMAGE_REQUIRED_STATUS}"
                f" & platforms = ({MATCH_GENRE_IMAGE_REQUIRED_PLATFORM})"
            )

            rows = igdb_client.query_games(
                fields="id,category,status,platforms,total_rating,total_rating_count,first_release_date,cover.url",
                where=where,
                sort="total_rating desc",
                limit=500,
                offset=0,
            )

            candidates: list[GenreImageCandidate] = []
            seen_game_ids: set[int] = set()

            for row in rows or []:
                try:
                    game_id = int(row.get("id") or 0)
                    category = int(row.get("category") or -1)
                    rating = float(row.get("total_rating") or 0.0)
                    rating_count = int(row.get("total_rating_count") or 0)
                    release_date = int(row.get("first_release_date") or 0)
                    cover_url = (row.get("cover") or {}).get("url")
                except TypeError:
                    continue
                except ValueError:
                    continue

                if game_id <= 0 or game_id in seen_game_ids:
                    continue
                if category not in MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES:
                    continue
                if rating < MATCH_GENRE_IMAGE_MIN_RATING:
                    continue
                if rating_count < MATCH_GENRE_IMAGE_MIN_RATING_COUNT:
                    continue
                if release_date < lookback_ts:
                    continue
                if not cover_url:
                    continue

                image_url = _normalize_cover_url(cover_url)
                if not image_url:
                    continue

                seen_game_ids.add(game_id)
                candidates.append(
                    GenreImageCandidate(
                        game_id=game_id,
                        image_url=image_url,
                        rating=rating,
                        rating_count=rating_count,
                    )
                )

            out[api_genre_id] = candidates

        return out

    def _save_map(self, image_map: dict[int, dict[str, Any]]) -> None:
        # TTL 없이 overwrite
        self.redis.set(self.cache_key, json.dumps(image_map, ensure_ascii=False))

    def run(self) -> dict[str, Any]:
        candidates_by_genre = self._fetch_candidates_by_genre()
        image_map = assign_genre_images(candidates_by_genre=candidates_by_genre)

        self._save_map(image_map)

        return {
            "cache_key": self.cache_key,
            "updated_count": len(image_map),
        }
