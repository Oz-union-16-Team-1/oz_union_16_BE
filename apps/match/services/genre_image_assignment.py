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


def _sort_candidates(
    candidates: Sequence[GenreImageCandidate],
) -> list[GenreImageCandidate]:
    # 배치 결과 안정화: rating > rating_count > game_id
    return sorted(
        candidates,
        key=lambda c: (c.rating, c.rating_count, c.game_id),
        reverse=True,
    )


def assign_genre_images(
    *,
    candidates_by_genre: Mapping[int, Sequence[GenreImageCandidate]],
    priority: Sequence[int] | None = None,
) -> dict[int, dict[str, Any]]:
    """
    장르 대표 이미지 배정 정책
    1) 우선순위 순서대로 장르를 처리
    2) 미사용 게임 중 최고 점수 선택
    3) 후보가 없으면 예외 발생 (배치 실패)
    """
    order = list(priority or GENRE_PRIORITY)

    used_game_ids: set[int] = set()
    result: dict[int, dict[str, Any]] = {}

    for api_genre_id in order:
        sorted_candidates = _sort_candidates(candidates_by_genre.get(api_genre_id, []))
        selected = next(
            (c for c in sorted_candidates if c.game_id not in used_game_ids), None
        )

        if selected is None:
            raise RuntimeError(f"genre_id={api_genre_id} 후보 게임이 없습니다.")

        used_game_ids.add(selected.game_id)
        result[api_genre_id] = {
            "game_id": selected.game_id,
            "image_url": selected.image_url,
            "rating": selected.rating,
            "rating_count": selected.rating_count,
        }

    return result
