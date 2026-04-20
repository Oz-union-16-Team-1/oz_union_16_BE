from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from apps.match.constants import GENRE_PRIORITY


@dataclass(frozen=True)
class GenreImageCandidate:
    game_id: int
    image_url: str
    rating: float
    rating_count: int = 0


def _sort_candidates(candidates: Sequence[GenreImageCandidate]) -> list[GenreImageCandidate]:
    # 배치 결과 안정화: rating > rating_count > game_id
    return sorted(
        candidates,
        key=lambda c: (c.rating, c.rating_count, c.game_id),
        reverse=True,
    )


def _to_candidate(item: Mapping[str, Any]) -> GenreImageCandidate | None:
    game_id = item.get("game_id")
    image_url = item.get("image_url")
    if game_id is None or not image_url:
        return None
    return GenreImageCandidate(
        game_id=int(game_id),
        image_url=str(image_url),
        rating=float(item.get("rating") or 0.0),
        rating_count=int(item.get("rating_count") or 0),
    )


def assign_genre_images(
    *,
    candidates_by_genre: Mapping[int, Sequence[GenreImageCandidate]],
    previous_map: Mapping[int, Mapping[str, Any]] | None = None,
    priority: Sequence[int] | None = None,
) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    """
    장르 대표 이미지 배정 정책 (중복 절대 금지)
    1) 미사용 게임 중 최고 점수 선택
    2) 없으면 이전 달 이미지 유지 시도(미사용일 때만)
    3) 그래도 없으면 missing 처리
    """
    order = list(priority or GENRE_PRIORITY)
    prev = previous_map or {}

    used_game_ids: set[int] = set()
    result: dict[int, dict[str, Any]] = {}

    stats = {
        "assigned_unique": 0,
        "fallback_previous": 0,
        "missing": 0,
    }

    for api_genre_id in order:
        sorted_candidates = _sort_candidates(candidates_by_genre.get(api_genre_id, []))

        selected = next((c for c in sorted_candidates if c.game_id not in used_game_ids), None)
        source = "unique"

        if selected is None:
            prev_item = prev.get(api_genre_id)
            prev_candidate = _to_candidate(prev_item) if prev_item else None
            if prev_candidate and prev_candidate.game_id not in used_game_ids:
                selected = prev_candidate
                source = "previous"

        if selected is None:
            stats["missing"] += 1
            continue

        used_game_ids.add(selected.game_id)
        result[api_genre_id] = {
            "game_id": selected.game_id,
            "image_url": selected.image_url,
            "rating": selected.rating,
            "rating_count": selected.rating_count,
            "source": source,
        }

        if source == "unique":
            stats["assigned_unique"] += 1
        else:
            stats["fallback_previous"] += 1

    return result, stats
