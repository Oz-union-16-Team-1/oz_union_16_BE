from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from apps.games.models import Game
from apps.match.constants import (
    API_TO_IGDB_GENRE_MAP,
    MATCH_CANDIDATE_MAX_COUNT,
    MATCH_CANDIDATE_POOL_SIZE,
)
from apps.match.models import MatchGameGenreMap, MatchGamePreference
from apps.users.models import UserLikeBookmark


@dataclass(frozen=True)
class CandidateItem:
    game_id: int
    vector: list[float]


class MatchCandidatesSelectorService:
    def select_game_ids(
        self,
        *,
        user_id: int,
        api_genre_id: int,
        retry_no: int = 0,
        today: date | None = None,
        max_count: int = MATCH_CANDIDATE_MAX_COUNT,
        pool_size: int = MATCH_CANDIDATE_POOL_SIZE,
    ) -> list[int]:
        target_genres = API_TO_IGDB_GENRE_MAP.get(api_genre_id, [])
        if not target_genres:
            return []

        liked_game_ids = set(
            UserLikeBookmark.objects.filter(user_id=user_id).values_list(
                "game_id", flat=True
            )
        )

        candidate_game_ids = sorted(
            set(
                MatchGameGenreMap.objects.filter(igdb_genre_id__in=target_genres)
                .exclude(game_id_id__in=liked_game_ids)
                .values_list("game_id_id", flat=True)
                .distinct()
            )
        )
        if not candidate_game_ids:
            return []

        allowed_game_ids = sorted(
            set(
                Game.objects.filter(
                    game_id__in=candidate_game_ids,
                    is_ban=False,
                ).values_list("game_id", flat=True)
            )
        )
        if not allowed_game_ids:
            return []

        candidates = self._load_vectors(allowed_game_ids)
        if not candidates:
            return []

        safe_retry_no = self._safe_retry_no(retry_no)
        rng = random.Random(
            self._seed(
                user_id=user_id,
                api_genre_id=api_genre_id,
                retry_no=safe_retry_no,
                today=today,
            )
        )

        pool = self._build_pool(candidates, rng=rng, pool_size=pool_size)
        selected = self._maximin_select(pool=pool, limit=max_count)
        return [item.game_id for item in selected]

    def _load_vectors(self, game_ids: Iterable[int]) -> list[CandidateItem]:
        rows = (
            MatchGamePreference.objects.filter(game_id_id__in=game_ids)
            .order_by("game_id_id")
            .values_list("game_id_id", "game_preference_vector")
        )

        out: list[CandidateItem] = []
        for game_id, raw_vector in rows:
            vector = self._normalize_vector(raw_vector)
            if vector:
                out.append(CandidateItem(game_id=game_id, vector=vector))
        return out

    def _normalize_vector(self, raw: object) -> list[float]:
        if not isinstance(raw, (list, tuple)):
            return []

        normalized: list[float] = []
        for value in raw:
            try:
                normalized.append(float(value))
            except TypeError, ValueError:
                return []
        return normalized

    def _build_pool(
        self,
        candidates: list[CandidateItem],
        *,
        rng: random.Random,
        pool_size: int,
    ) -> list[CandidateItem]:
        if len(candidates) <= pool_size:
            pool = list(candidates)
            rng.shuffle(pool)
            return pool
        return rng.sample(candidates, pool_size)

    def _maximin_select(
        self,
        *,
        pool: list[CandidateItem],
        limit: int,
    ) -> list[CandidateItem]:
        if not pool:
            return []

        selected: list[CandidateItem] = [pool[0]]
        remaining = pool[1:]

        while remaining and len(selected) < limit:
            best_index = 0
            best_score = -1.0

            for idx, cand in enumerate(remaining):
                score = min(
                    self._cosine_distance(cand.vector, picked.vector)
                    for picked in selected
                )
                if score > best_score:
                    best_score = score
                    best_index = idx

            selected.append(remaining.pop(best_index))

        return selected

    def _cosine_distance(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 1.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 1.0

        cosine_similarity = dot / (norm_a * norm_b)
        cosine_similarity = max(-1.0, min(1.0, cosine_similarity))
        return 1.0 - cosine_similarity

    def _seed(
        self,
        *,
        user_id: int,
        api_genre_id: int,
        retry_no: int,
        today: date | None,
    ) -> int:
        base_day = today or date.today()
        raw = f"{user_id}:{api_genre_id}:{base_day.isoformat()}:{retry_no}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return int(digest[:16], 16)

    def _safe_retry_no(self, retry_no: int) -> int:
        try:
            return max(0, int(retry_no))
        except TypeError, ValueError:
            return 0
