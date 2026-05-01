from __future__ import annotations

from datetime import timedelta
from typing import TypedDict

from django.db.models import FloatField, IntegerField, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.games.models import Game
from apps.match.constants import (
    API_TO_IGDB_IMAGE_GENRE_MAP,
    GENRE_PRIORITY,
    MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES,
    MATCH_GENRE_IMAGE_MAX_LOOKBACK_YEARS,
    MATCH_GENRE_IMAGE_MIN_RATING,
    MATCH_GENRE_IMAGE_MIN_RATING_COUNT,
    MATCH_GENRE_IMAGE_MONTHLY_END_MONTH,
    MATCH_GENRE_IMAGE_MONTHLY_START_DAYS,
    MATCH_GENRE_IMAGE_REQUIRED_STATUS,
    MATCH_GENRE_IMAGE_YEARLY_END,
    MATCH_GENRE_IMAGE_YEARLY_START,
)
from apps.match.services.genre_image_assets import (
    ImageOption,
    build_cover_option,
    build_screenshot_options,
    fetch_artwork_options_map,
    merge_unique_image_options,
)


class GenreImageCandidate(TypedDict):
    game_id: int
    name: str
    rating: float
    rating_count: int
    release_ts: int
    images: list[ImageOption]


class GenreImageCandidatesService:
    def __init__(self, scan_limit: int = 2000) -> None:
        self.scan_limit = scan_limit

    def build_candidates_by_genre(
        self, limit_per_genre: int = 5
    ) -> dict[int, list[GenreImageCandidate]]:
        ranked_by_genre: dict[int, list[GenreImageCandidate]] = {}
        for genre_id in range(1, 9):
            ranked_by_genre[genre_id] = self._fetch_ranked_candidates_for_genre(
                api_genre_id=genre_id,
                scan_limit=self.scan_limit,
            )

        now_ts = int(timezone.now().timestamp())
        selected: dict[int, list[GenreImageCandidate]] | None = None

        for days in self._build_cutoff_days():
            cutoff_ts = now_ts - (days * 24 * 60 * 60)

            filtered_by_genre: dict[int, list[GenreImageCandidate]] = {}
            for genre_id, rows in ranked_by_genre.items():
                filtered_by_genre[genre_id] = [
                    r for r in rows if int(r.get("release_ts", 0)) >= cutoff_ts
                ]

            picked = self._assign_with_priority(
                ranked_by_genre=filtered_by_genre,
                limit_per_genre=limit_per_genre,
            )

            # 장르별 최소 limit_per_genre 확보 시 종료
            if all(len(picked.get(gid, [])) >= limit_per_genre for gid in range(1, 9)):
                selected = picked
                break

        if selected is None:
            selected = self._assign_with_priority(
                ranked_by_genre=ranked_by_genre,
                limit_per_genre=limit_per_genre,
            )

        selected = self._backfill_short_genres(
            selected_by_genre=selected,
            ranked_by_genre=ranked_by_genre,
            limit_per_genre=limit_per_genre,
        )

        self._attach_artworks(selected)
        return selected

    def _build_cutoff_days(self) -> list[int]:
        monthly = [
            MATCH_GENRE_IMAGE_MONTHLY_START_DAYS * i
            for i in range(1, MATCH_GENRE_IMAGE_MONTHLY_END_MONTH + 1)
        ]
        yearly = [
            365 * y
            for y in range(
                MATCH_GENRE_IMAGE_YEARLY_START, MATCH_GENRE_IMAGE_YEARLY_END + 1
            )
        ]
        return monthly + yearly

    def _assign_with_priority(
        self,
        ranked_by_genre: dict[int, list[GenreImageCandidate]],
        limit_per_genre: int,
    ) -> dict[int, list[GenreImageCandidate]]:
        selected_by_genre: dict[int, list[GenreImageCandidate]] = {
            gid: [] for gid in range(1, 9)
        }
        used_game_ids: set[int] = set()

        for genre_id in GENRE_PRIORITY:
            ranked = ranked_by_genre.get(genre_id, [])
            chosen: list[GenreImageCandidate] = []
            chosen_ids: set[int] = set()

            # 1차: 장르 간 중복 제거
            for c in ranked:
                gid = int(c["game_id"])
                if gid in used_game_ids:
                    continue
                chosen.append(c)
                chosen_ids.add(gid)
                if len(chosen) >= limit_per_genre:
                    break

            # 2차: 부족분은 장르 내부 중복허용 보충(=이미 사용된 게임도 허용)
            if len(chosen) < limit_per_genre:
                for c in ranked:
                    gid = int(c["game_id"])
                    if gid in chosen_ids:
                        continue
                    chosen.append(c)
                    chosen_ids.add(gid)
                    if len(chosen) >= limit_per_genre:
                        break

            selected_by_genre[genre_id] = chosen[:limit_per_genre]
            used_game_ids.update(chosen_ids)

        return selected_by_genre

    def _backfill_short_genres(
        self,
        selected_by_genre: dict[int, list[GenreImageCandidate]],
        ranked_by_genre: dict[int, list[GenreImageCandidate]],
        limit_per_genre: int,
    ) -> dict[int, list[GenreImageCandidate]]:
        out = {gid: list(rows) for gid, rows in selected_by_genre.items()}

        for genre_id in range(1, 9):
            cur = out.get(genre_id, [])
            if len(cur) >= limit_per_genre:
                continue

            chosen_ids = {int(x["game_id"]) for x in cur}
            for c in ranked_by_genre.get(genre_id, []):
                gid = int(c["game_id"])
                if gid in chosen_ids:
                    continue
                cur.append(c)
                chosen_ids.add(gid)
                if len(cur) >= limit_per_genre:
                    break

            out[genre_id] = cur

        return out

    def _fetch_ranked_candidates_for_genre(
        self,
        api_genre_id: int,
        scan_limit: int = 2000,
    ) -> list[GenreImageCandidate]:
        igdb_genre_ids = API_TO_IGDB_IMAGE_GENRE_MAP.get(api_genre_id, [])
        if not igdb_genre_ids:
            return []

        genre_q = Q()
        for gid in igdb_genre_ids:
            genre_q |= Q(genres__contains=[gid])

        if not genre_q.children:
            return []

        cutoff_dt = timezone.now() - timedelta(
            days=MATCH_GENRE_IMAGE_MAX_LOOKBACK_YEARS * 365
        )

        rows = (
            Game.objects.filter(genre_q, is_ban=False)
            .filter(first_release_date__isnull=False, first_release_date__gte=cutoff_dt)
            .filter(
                Q(category__isnull=True)
                | Q(category__in=MATCH_GENRE_IMAGE_ALLOWED_CATEGORIES)
            )
            .filter(
                Q(status__isnull=True) | Q(status=MATCH_GENRE_IMAGE_REQUIRED_STATUS)
            )
            .annotate(
                score_rating=Coalesce(
                    "total_rating", "rating", output_field=FloatField()
                ),
                score_count=Coalesce(
                    "total_rating_count", "rating_count", output_field=IntegerField()
                ),
            )
            .filter(
                score_rating__gte=MATCH_GENRE_IMAGE_MIN_RATING,
                score_count__gte=MATCH_GENRE_IMAGE_MIN_RATING_COUNT,
            )
            .values(
                "game_id",
                "name",
                "cover",
                "screenshots",
                "score_rating",
                "score_count",
                "first_release_date",
            )
            .order_by(
                "-first_release_date",
                "-score_rating",
                "-score_count",
                "-game_id",
            )[:scan_limit]
        )

        out: list[GenreImageCandidate] = []
        for row in rows:
            images = merge_unique_image_options(
                build_cover_option(row.get("cover"))
                + build_screenshot_options(row.get("screenshots"))
            )
            if not images:
                continue

            release_dt = row.get("first_release_date")
            release_ts = int(release_dt.timestamp()) if release_dt is not None else 0

            out.append(
                GenreImageCandidate(
                    game_id=int(row["game_id"]),
                    name=str(row.get("name") or ""),
                    rating=round(float(row.get("score_rating") or 0.0), 2),
                    rating_count=int(row.get("score_count") or 0),
                    release_ts=release_ts,
                    images=images,
                )
            )

        return out

    def _attach_artworks(
        self, selected_by_genre: dict[int, list[GenreImageCandidate]]
    ) -> None:
        game_ids: list[int] = []
        for candidates in selected_by_genre.values():
            for c in candidates:
                game_ids.append(int(c["game_id"]))

        artwork_map = fetch_artwork_options_map(game_ids)
        if not artwork_map:
            return

        for candidates in selected_by_genre.values():
            for c in candidates:
                gid = int(c["game_id"])
                c["images"] = merge_unique_image_options(
                    c["images"] + artwork_map.get(gid, [])
                )
