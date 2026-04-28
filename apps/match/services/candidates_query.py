from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.games.models import Game
from apps.match.constants import IGDB_GENRE_NAME_MAP
from apps.match.models import MatchCandidateRetryState, MatchGameGenreMap
from apps.match.services.candidates_selector import MatchCandidatesSelectorService
from apps.users.models import UserLikeBookmark

DESCRIPTION_MAX_CHARS = 200  # PC 카드 기준 2~3줄 목표


class MatchCandidatesDataUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "외부 게임 데이터 서비스가 일시적으로 불가합니다."


class MatchCandidatesQueryService:
    selector_class = MatchCandidatesSelectorService

    def get_candidates(
        self,
        *,
        user_id: int,
        genre_id: int,
        retry_no: int | None = None,
    ) -> dict[str, Any]:
        try:
            effective_retry_no = self._resolve_effective_retry_no(
                user_id=user_id,
                genre_id=genre_id,
                retry_no=retry_no,
            )

            selected_ids = self.selector_class().select_game_ids(
                user_id=user_id,
                api_genre_id=genre_id,
                retry_no=effective_retry_no,
            )
            if not selected_ids:
                return {
                    "genre_id": genre_id,
                    "retry_no": effective_retry_no,
                    "count": 0,
                    "results": [],
                }

            game_rows = list(
                Game.objects.filter(game_id__in=selected_ids, is_ban=False).values(
                    "game_id",
                    "name",
                    "videos",
                    "summary",
                    "storyline",
                    "rating",
                )
            )
            if not game_rows:
                return {
                    "genre_id": genre_id,
                    "retry_no": effective_retry_no,
                    "count": 0,
                    "results": [],
                }

            game_map = {int(row["game_id"]): row for row in game_rows}
            ordered_ids = [gid for gid in selected_ids if gid in game_map]
            if not ordered_ids:
                return {
                    "genre_id": genre_id,
                    "retry_no": effective_retry_no,
                    "count": 0,
                    "results": [],
                }

            liked_ids = set(
                UserLikeBookmark.objects.filter(
                    user_id=user_id,
                    game_id__in=ordered_ids,
                ).values_list("game_id", flat=True)
            )

            genre_rows = MatchGameGenreMap.objects.filter(
                game_id_id__in=ordered_ids
            ).values_list("game_id_id", "igdb_genre_id")

            genres_by_game: dict[int, list[str]] = defaultdict(list)
            for game_id, igdb_genre_id in genre_rows:
                game_id_int = int(game_id)
                genre_name = IGDB_GENRE_NAME_MAP.get(int(igdb_genre_id))
                if genre_name and genre_name not in genres_by_game[game_id_int]:
                    genres_by_game[game_id_int].append(genre_name)

            results: list[dict[str, Any]] = []
            for game_id in ordered_ids:
                row = game_map[game_id]

                results.append(
                    {
                        "game_id": game_id,
                        "title": str(row.get("name") or ""),
                        "trailer_url": self._to_trailer_url(row.get("videos")),
                        "is_liked": game_id in liked_ids,
                        "description": self._normalize_description(
                            row.get("summary"),
                            row.get("storyline"),
                        ),
                        "genres": genres_by_game.get(game_id, []),
                        "rating": self._normalize_rating(row.get("rating")),
                    }
                )

            return {
                "genre_id": genre_id,
                "retry_no": effective_retry_no,
                "count": len(results),
                "results": results,
            }
        except APIException:
            raise
        except Exception as exc:
            raise MatchCandidatesDataUnavailable() from exc

    def _normalize_description(self, summary: object, storyline: object) -> str:
        base = str(summary or "").strip() or str(storyline or "").strip()
        text = re.sub(r"\s+", " ", base).strip()

        if len(text) <= DESCRIPTION_MAX_CHARS:
            return text

        cut = text[: DESCRIPTION_MAX_CHARS + 1]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]

        return f"{cut.rstrip()}…"

    def _normalize_rating(self, rating: object) -> float:
        if rating is None:
            return 0.0
        if isinstance(rating, bool):
            return 0.0

        rating_value: Any = rating
        try:
            return round(float(rating_value), 1)
        except TypeError:
            return 0.0
        except ValueError:
            return 0.0

    def _to_trailer_url(self, videos: object) -> str:
        if not isinstance(videos, list) or not videos:
            return ""

        first = videos[0]
        if isinstance(first, dict):
            first = first.get("video_id") or first.get("id") or ""

        video_id = str(first or "").strip()
        if not video_id:
            return ""

        if video_id.startswith("http://") or video_id.startswith("https://"):
            return video_id

        return f"https://www.youtube.com/watch?v={video_id}"

    def _resolve_effective_retry_no(
        self,
        *,
        user_id: int,
        genre_id: int,
        retry_no: int | None,
    ) -> int:
        if retry_no is not None:
            return max(0, int(retry_no))

        today = timezone.localdate()
        state = (
            MatchCandidateRetryState.objects.filter(
                user_id=user_id,
                api_genre_id=genre_id,
                candidate_date=today,
            )
            .only("last_completed_retry_no")
            .first()
        )
        if state is None:
            return 0

        return max(0, int(state.last_completed_retry_no) + 1)
