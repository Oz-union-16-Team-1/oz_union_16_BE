from __future__ import annotations

import base64
import json
import math
import re
import time
from collections import defaultdict
from collections.abc import Iterable as IterableABC
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from django.db.models import DateTimeField, FloatField, IntegerField, Value
from django.db.models.functions import Coalesce
from pgvector.django import CosineDistance

from apps.games.models import Game
from apps.match.constants import (
    API_TO_IGDB_GENRE_MAP,
    IGDB_GENRE_NAME_MAP,
    MATCH_RESULT_DEFAULT_PAGE_SIZE,
    MATCH_RESULT_LIKED_RATIO_CAP,
    MATCH_RESULT_LIKED_TOP_K,
    MATCH_RESULT_MAX_PAGE_SIZE,
    MATCH_RESULT_MAX_TOTAL_COUNT,
    MATCH_RESULT_POP_BOOST,
    MATCH_RESULT_POP_DEFAULT,
    MATCH_RESULT_RECENCY_WINDOW_DAYS,
    MATCH_RESULT_SCORE_NORMALIZER,
    MATCH_RESULT_SIM_FLOOR,
    MATCH_RESULT_SIM_VECTOR_DIM,
    MATCH_RESULT_SIM_GENRE_WEIGHT,
    MATCH_RESULT_SIM_MOOD_WEIGHT,
    MATCH_RESULT_TAU_FINAL_STEPS,
    MATCH_RESULT_WEIGHT_DISLIKE_PENALTY,
    MATCH_RESULT_WEIGHT_LIKE_BONUS,
    MATCH_RESULT_WEIGHT_POP,
    MATCH_RESULT_WEIGHT_REC,
    MATCH_RESULT_WEIGHT_SIM,

)
from apps.match.models import MatchGameGenreMap, MatchGamePreference, MatchGameRating
from apps.users.models import UserLikeBookmark, UserPreference


class MatchResponsesResultValidationError(ValueError):
    pass


class MatchResponsesResultDataUnavailable(RuntimeError):
    pass


SERIES_SUFFIX_RE = re.compile(
    r"(?:[-_ ](?:deluxe|ultimate|complete|definitive|gold|goty|edition|bundle|pack|collection|remaster(?:ed)?|remake|director(?:s)?[-_ ]?cut|anniversary))+$",
    re.IGNORECASE,
)
TITLE_NOISE_RE = re.compile(r"[\(\[\{].*?[\)\]\}]")


@dataclass(frozen=True)
class RankedGame:
    game_id: int
    title: str
    slug: str
    genres: list[str]
    thumbnail_url: str
    rating: float
    is_liked: bool
    final_score: float
    pop_score: float
    rec_score: float


class MatchResponsesResultQueryService:
    MAX_SIM_SCAN = 5000
    MIN_FALLBACK_SCAN = 200
    FALLBACK_SCAN_MULTIPLIER = 20
    DEDUPE_OVERFETCH_FACTOR = 3

    def get_results(
        self,
        *,
        user_id: int,
        genre_id: int,
        cursor: str | None = None,
        page_size: int = MATCH_RESULT_DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        try:
            size = self._normalize_page_size(page_size)
            liked_ids = self._liked_ids(user_id=user_id)
            allowed_ids = self._allowed_game_ids_by_genre(genre_id=genre_id)

            if not allowed_ids:
                return {
                    "user_id": user_id,
                    "count": 0,
                    "next": None,
                    "results": [],
                }

            selected: list[RankedGame] = []
            target_count = MATCH_RESULT_MAX_TOTAL_COUNT
            selection_target = max(
                target_count,
                target_count * self.DEDUPE_OVERFETCH_FACTOR,
            )
            user_vector = self._load_user_vector(user_id=user_id)

            if user_vector:
                liked_mean = self._load_liked_mean_vector(user_id=user_id)
                disliked_mean = self._load_disliked_mean_vector(user_id=user_id)

                # 핵심 최적화: 개인화 스코어링 쿼리는 1회만 수행
                personalized_all = self._score_personalized_once(
                    user_vector=user_vector,
                    sim_floor=MATCH_RESULT_SIM_FLOOR,
                    liked_ids=liked_ids,
                    liked_mean_vector=liked_mean,
                    disliked_mean_vector=disliked_mean,
                )

                # 0순위: 선택 장르 + liked 제외 + sim >= 0.20 + TAU 단계 완화
                stage0 = [
                    item
                    for item in personalized_all
                    if item.game_id in allowed_ids and not item.is_liked
                ]
                selected = self._merge_unique(
                    selected,
                    self._apply_tau_steps(stage0, limit=selection_target),
                )

                # 1순위: 선택 장르 + liked only + sim >= 0.20 + TAU 단계 완화
                # liked 보충은 전체 결과의 30% 캡
                if len(selected) < selection_target:
                    liked_cap = self._liked_cap(target_count)
                    room_for_liked = max(0, liked_cap - self._count_liked(selected))
                    if room_for_liked > 0:
                        stage1 = [
                            item
                            for item in personalized_all
                            if item.game_id in allowed_ids and item.is_liked
                        ]
                        stage1 = self._apply_tau_steps(stage1, limit=selection_target)
                        stage1 = self._take_by_popularity(stage1, room_for_liked)
                        selected = self._merge_unique(selected, stage1)

                # 2순위: 전체 + liked 제외 + sim >= 0.20 + 인기순
                if len(selected) < selection_target:
                    used_ids = {item.game_id for item in selected}
                    stage2 = [
                        item
                        for item in personalized_all
                        if (not item.is_liked) and item.game_id not in used_ids
                    ]
                    stage2 = self._take_by_popularity(
                        stage2,
                        selection_target - len(selected),
                    )
                    selected = self._merge_unique(selected, stage2)

            # 3순위: 선택 장르 + sim 제거 + 인기순
            if len(selected) < selection_target:
                stage3 = self._fallback_popular(
                    source_ids=allowed_ids,
                    excluded_ids=liked_ids.union({item.game_id for item in selected}),
                    limit=selection_target - len(selected),
                    liked_ids=liked_ids,
                )
                selected = self._merge_unique(selected, stage3)

            # 4순위: 전체 + sim 제거 + 인기순
            if len(selected) < selection_target:
                stage4 = self._fallback_popular(
                    source_ids=None,
                    excluded_ids=liked_ids.union({item.game_id for item in selected}),
                    limit=selection_target - len(selected),
                    liked_ids=liked_ids,
                )
                selected = self._merge_unique(selected, stage4)

            sorted_ranked = sorted(
                selected,
                key=lambda item: (item.final_score, item.game_id),
                reverse=True,
            )

            deduped_top = self._dedupe_series_variants(
                sorted_ranked,
                limit=target_count,
            )

            final_ranked = self._fill_after_dedupe(
                deduped_top=deduped_top,
                ranked_pool=sorted_ranked,
                limit=target_count,
            )

            page_items, next_cursor = self._paginate(
                items=final_ranked,
                cursor=cursor,
                page_size=size,
            )

            return {
                "user_id": user_id,
                "count": len(final_ranked),
                "next": next_cursor,
                "results": [
                    {
                        "game_id": item.game_id,
                        "title": item.title,
                        "genres": item.genres,
                        "thumbnail_url": item.thumbnail_url,
                        "rating": item.rating,
                        "is_liked": item.is_liked,
                    }
                    for item in page_items
                ],
            }
        except MatchResponsesResultValidationError:
            raise
        except Exception as exc:
            raise MatchResponsesResultDataUnavailable(
                "추천 데이터 조회 중 외부 서비스 오류가 발생했습니다."
            ) from exc

    def _normalize_page_size(self, page_size: int) -> int:
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            return MATCH_RESULT_DEFAULT_PAGE_SIZE
        if page_size < 1:
            return MATCH_RESULT_DEFAULT_PAGE_SIZE
        return min(page_size, MATCH_RESULT_MAX_PAGE_SIZE)

    def _liked_ids(self, *, user_id: int) -> set[int]:
        return set(
            UserLikeBookmark.objects.filter(user_id=user_id).values_list(
                "game_id",
                flat=True,
            )
        )

    def _allowed_game_ids_by_genre(self, *, genre_id: int) -> set[int]:
        target_genres = API_TO_IGDB_GENRE_MAP.get(genre_id, [])
        if not target_genres:
            return set()

        return set(
            MatchGameGenreMap.objects.filter(igdb_genre_id__in=target_genres)
            .values_list("game_id_id", flat=True)
            .distinct()
        )

    def _load_user_vector(self, *, user_id: int) -> list[float] | None:
        raw = (
            UserPreference.objects.filter(user_id=user_id)
            .values_list("match_vector", flat=True)
            .first()
        )
        vec = self._to_vector(raw)
        return vec if vec else None

    def _score_personalized_once(
        self,
        *,
        user_vector: list[float],
        sim_floor: float,
        liked_ids: set[int],
        liked_mean_vector: list[float] | None,
        disliked_mean_vector: list[float] | None,
    ) -> list[RankedGame]:
        # result sim은 dim1~13만 사용 (dim14 인기도 제외)
        sim_user_vector = self._result_sim_vector(user_vector)
        if not sim_user_vector:
            return []

        # DB distance는 스캔 순서 최적화용, 실제 sim floor/점수 계산은 앱 레벨(13차원)에서 적용
        qs = MatchGamePreference.objects.annotate(
            distance=CosineDistance("game_preference_vector", user_vector)
        )

        rows = list(
            qs.order_by("distance", "game_id_id").values_list(
                "game_id_id",
                "game_preference_vector",
                "distance",
            )[: self.MAX_SIM_SCAN]
        )
        if not rows:
            return []

        vectors_by_game: dict[int, list[float]] = {}
        sim_by_game: dict[int, float] = {}

        for game_id, raw_vector, _distance in rows:
            game_id_int = int(game_id)
            parsed_vec = self._to_vector(raw_vector)
            if not parsed_vec:
                continue

            sim_game_vector = self._result_sim_vector(parsed_vec)
            if not sim_game_vector:
                continue

            sim = self._result_split_similarity(sim_game_vector, sim_user_vector)
            sim = max(0.0, min(1.0, sim))
            if sim < sim_floor:
                continue

            vectors_by_game[game_id_int] = parsed_vec
            sim_by_game[game_id_int] = sim

        if not vectors_by_game:
            return []

        game_rows = list(
            Game.objects.filter(
                game_id__in=set(vectors_by_game.keys()),
                is_ban=False,
            ).values(
                "game_id",
                "name",
                "slug",
                "cover",
                "rating",
                "first_release_date",
                "rating_count",
            )
        )
        if not game_rows:
            return []

        genre_map = self._genres_by_game(set(vectors_by_game.keys()))
        ranked: list[RankedGame] = []

        liked_mean_sim_vector = (
            self._result_sim_vector(liked_mean_vector) if liked_mean_vector else None
        )
        disliked_mean_sim_vector = (
            self._result_sim_vector(disliked_mean_vector)
            if disliked_mean_vector
            else None
        )

        for row in game_rows:
            game_id = int(row["game_id"])
            game_vec = vectors_by_game.get(game_id)
            if game_vec is None:
                continue

            game_sim_vec = self._result_sim_vector(game_vec)
            if not game_sim_vec:
                continue

            sim = sim_by_game.get(game_id, 0.0)
            pop = self._to_pop_score(row.get("rating"))
            rec = self._to_rec_score(row.get("first_release_date"))

            like_bonus = 0.0
            if liked_mean_sim_vector:
                like_bonus = max(
                    0.0, self._result_split_similarity(game_sim_vec, liked_mean_sim_vector)
                )

            dislike_penalty = 0.0
            if disliked_mean_sim_vector:
                dislike_penalty = max(
                    0.0, self._result_split_similarity(game_sim_vec, disliked_mean_sim_vector)
                )

            final_score = self._compose_final_score(
                sim=sim,
                pop=pop,
                rec=rec,
                like_bonus=like_bonus,
                dislike_penalty=dislike_penalty,
            )

            ranked.append(
                RankedGame(
                    game_id=game_id,
                    title=str(row.get("name") or ""),
                    slug=str(row.get("slug") or ""),
                    genres=genre_map.get(game_id, []),
                    thumbnail_url=self._to_thumbnail_url(row.get("cover")),
                    rating=self._normalize_rating(row.get("rating")),
                    is_liked=game_id in liked_ids,
                    final_score=final_score,
                    pop_score=pop,
                    rec_score=rec,
                )
            )

        return sorted(
            ranked,
            key=lambda item: (item.final_score, item.game_id),
            reverse=True,
        )

    def _apply_tau_steps(
        self,
        ranked: list[RankedGame],
        *,
        limit: int = MATCH_RESULT_MAX_TOTAL_COUNT,
    ) -> list[RankedGame]:
        if not ranked:
            return []

        for tau in MATCH_RESULT_TAU_FINAL_STEPS:
            filtered = [item for item in ranked if item.final_score >= tau]
            if len(filtered) >= limit:
                return filtered[:limit]

        min_tau = MATCH_RESULT_TAU_FINAL_STEPS[-1]
        return [item for item in ranked if item.final_score >= min_tau]

    def _fallback_popular(
        self,
        *,
        source_ids: set[int] | None,
        excluded_ids: set[int],
        limit: int,
        liked_ids: set[int],
    ) -> list[RankedGame]:
        if limit <= 0:
            return []

        qs = Game.objects.filter(is_ban=False).exclude(game_id__in=excluded_ids)
        if source_ids is not None:
            if not source_ids:
                return []
            qs = qs.filter(game_id__in=source_ids)

        scan_size = max(self.MIN_FALLBACK_SCAN, limit * self.FALLBACK_SCAN_MULTIPLIER)

        # 슬라이스 전에 DB에서 인기순 정렬을 확정해서 "전체 상위" 후보를 가져온다.
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        qs = qs.annotate(
            _rating_order=Coalesce("rating", Value(50.0), output_field=FloatField()),
            _release_order=Coalesce(
                "first_release_date",
                Value(epoch),
                output_field=DateTimeField(),
            ),
            _rating_count_order=Coalesce(
                "rating_count",
                Value(0),
                output_field=IntegerField(),
            ),
        ).order_by(
            "-_rating_order",
            "-_release_order",
            "-_rating_count_order",
            "-game_id",
        )

        rows = list(
            qs.values(
                "game_id",
                "name",
                "slug",
                "cover",
                "rating",
                "rating_count",
                "first_release_date",
            )[:scan_size]
        )
        if not rows:
            return []

        # 기존 점수 체계(pop/rec)로 최종 컷
        rows.sort(
            key=lambda row: (
                self._to_pop_score(row.get("rating")),
                self._to_rec_score(row.get("first_release_date")),
                int(row.get("rating_count") or 0),
                int(row.get("game_id") or 0),
            ),
            reverse=True,
        )

        picked = rows[:limit]
        picked_ids = {int(row["game_id"]) for row in picked}
        genre_map = self._genres_by_game(picked_ids)

        out: list[RankedGame] = []
        for row in picked:
            game_id = int(row["game_id"])
            pop = self._to_pop_score(row.get("rating"))
            rec = self._to_rec_score(row.get("first_release_date"))

            final_raw = (pop * MATCH_RESULT_WEIGHT_POP) + (
                rec * MATCH_RESULT_WEIGHT_REC
            )
            final_score = self._compose_final_score(
                sim=0.0,
                pop=pop,
                rec=rec,
                like_bonus=0.0,
                dislike_penalty=0.0,
            )

            out.append(
                RankedGame(
                    game_id=game_id,
                    title=str(row.get("name") or ""),
                    slug=str(row.get("slug") or ""),
                    genres=genre_map.get(game_id, []),
                    thumbnail_url=self._to_thumbnail_url(row.get("cover")),
                    rating=self._normalize_rating(row.get("rating")),
                    is_liked=game_id in liked_ids,
                    final_score=final_score,
                    pop_score=pop,
                    rec_score=rec,
                )
            )

        return out

    def _load_liked_mean_vector(self, *, user_id: int) -> list[float] | None:
        top_liked_ids = list(
            UserLikeBookmark.objects.filter(user_id=user_id)
            .order_by("-created_at")
            .values_list("game_id", flat=True)[:MATCH_RESULT_LIKED_TOP_K]
        )
        return self._mean_vector_for_game_ids(top_liked_ids)

    def _load_disliked_mean_vector(self, *, user_id: int) -> list[float] | None:
        one_star_ids = list(
            MatchGameRating.objects.filter(user_id=user_id, star_rating=1).values_list(
                "game_id",
                flat=True,
            )
        )
        return self._mean_vector_for_game_ids(one_star_ids)

    def _mean_vector_for_game_ids(self, game_ids: list[int]) -> list[float] | None:
        if not game_ids:
            return None

        rows = MatchGamePreference.objects.filter(game_id_id__in=game_ids).values_list(
            "game_preference_vector",
            flat=True,
        )

        vectors: list[list[float]] = []
        for raw in rows:
            vec = self._to_vector(raw)
            if vec:
                vectors.append(vec)

        if not vectors:
            return None

        dim = len(vectors[0])
        for vec in vectors:
            if len(vec) != dim:
                return None

        acc = [0.0] * dim
        for vec in vectors:
            for idx, value in enumerate(vec):
                acc[idx] += value

        size = float(len(vectors))
        return [value / size for value in acc]

    def _genres_by_game(self, game_ids: set[int]) -> dict[int, list[str]]:
        if not game_ids:
            return {}

        rows = (
            MatchGameGenreMap.objects.filter(game_id_id__in=game_ids)
            .order_by("game_id_id", "igdb_genre_id")
            .values_list("game_id_id", "igdb_genre_id")
        )

        out: dict[int, list[str]] = defaultdict(list)
        for game_id, igdb_genre_id in rows:
            gid = int(game_id)
            genre_name = IGDB_GENRE_NAME_MAP.get(int(igdb_genre_id))
            if genre_name and genre_name not in out[gid]:
                out[gid].append(genre_name)

        return dict(out)

    def _paginate(
        self,
        *,
        items: list[RankedGame],
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[RankedGame], str | None]:
        if not items:
            return [], None

        start = 0
        if cursor:
            c_score, c_game_id, c_offset = self._decode_cursor(cursor)

            found = False
            for idx, item in enumerate(items):
                if (item.final_score < c_score) or (
                    item.final_score == c_score and item.game_id < c_game_id
                ):
                    start = idx
                    found = True
                    break

            # 좋아요 토글 등으로 집합이 변해 (score, game_id) anchor를 못 찾는 경우
            # 커서 offset으로 fallback 해서 "더보기 무응답"을 방지한다.
            if not found:
                if c_offset is not None:
                    # 빈 페이지가 되지 않도록 안전 clamp
                    start = min(max(c_offset, 0), max(len(items) - 1, 0))
                else:
                    start = len(items)

        page = items[start : start + page_size]
        if not page:
            return [], None

        has_next = (start + page_size) < len(items)
        next_cursor = None
        if has_next:
            last = page[-1]
            next_cursor = self._encode_cursor(
                last.final_score,
                last.game_id,
                offset=start + page_size,
            )

        return page, next_cursor

    def _encode_cursor(
        self, score: float, game_id: int, offset: int | None = None
    ) -> str:
        obj: dict[str, int | float] = {
            "s": round(float(score), 6),
            "g": int(game_id),
        }
        if offset is not None:
            obj["o"] = int(offset)

        payload = json.dumps(
            obj,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return (
            base64.urlsafe_b64encode(payload.encode("utf-8"))
            .decode("utf-8")
            .rstrip("=")
        )

    def _decode_cursor(self, cursor: str) -> tuple[float, int, int | None]:
        try:
            padded = cursor + ("=" * (-len(cursor) % 4))
            raw = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            obj = json.loads(raw)

            score = round(float(obj["s"]), 6)
            game_id = int(obj["g"])
            offset_raw = obj.get("o")
            offset = int(offset_raw) if offset_raw is not None else None

            return score, game_id, offset
        except Exception as exc:
            raise MatchResponsesResultValidationError(
                "cursor 형식이 올바르지 않습니다."
            ) from exc

    def _merge_unique(
        self,
        base: list[RankedGame],
        extra: list[RankedGame],
    ) -> list[RankedGame]:
        seen = {item.game_id for item in base}
        out = list(base)
        for item in extra:
            if item.game_id in seen:
                continue
            seen.add(item.game_id)
            out.append(item)
        return out

    def _dedupe_series_variants(
        self,
        items: list[RankedGame],
        *,
        limit: int,
    ) -> list[RankedGame]:
        """
        상위 limit 구간에서 같은 시리즈/에디션 중복을 제거한다.
        """
        if not items or limit <= 0:
            return []

        out: list[RankedGame] = []
        seen_keys: set[str] = set()

        for item in items[:limit]:
            key = self._canonical_game_key(item)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            out.append(item)

        return out

    def _fill_after_dedupe(
        self,
        *,
        deduped_top: list[RankedGame],
        ranked_pool: list[RankedGame],
        limit: int,
    ) -> list[RankedGame]:
        """
        dedupe로 limit 미만이 되면, 정렬된 원본 풀에서
        아직 사용되지 않은 canonical key를 순서대로 보충한다.
        """
        if limit <= 0:
            return []

        out = list(deduped_top)
        if len(out) >= limit:
            return out[:limit]

        seen_game_ids = {item.game_id for item in out}
        seen_keys = {self._canonical_game_key(item) for item in out}

        for item in ranked_pool:
            if item.game_id in seen_game_ids:
                continue

            key = self._canonical_game_key(item)
            if key in seen_keys:
                continue

            seen_game_ids.add(item.game_id)
            seen_keys.add(key)
            out.append(item)

            if len(out) >= limit:
                break

        return out[:limit]

    def _canonical_game_key(self, item: RankedGame) -> str:
        slug_key = self._normalize_slug_for_dedupe(item.slug)
        if slug_key:
            return f"s:{slug_key}"

        title_key = self._normalize_title_for_dedupe(item.title)
        return f"t:{title_key}"

    def _normalize_slug_for_dedupe(self, slug: str) -> str:
        text = (slug or "").strip().lower()
        if not text:
            return ""

        text = SERIES_SUFFIX_RE.sub("", text)
        text = re.sub(r"[-_]+", "-", text).strip("-")
        return text

    def _normalize_title_for_dedupe(self, title: str) -> str:
        text = (title or "").strip().lower()
        if not text:
            return ""

        text = TITLE_NOISE_RE.sub(" ", text)  # 괄호 부가정보 제거
        text = SERIES_SUFFIX_RE.sub("", text)
        text = re.sub(r"[^a-z0-9가-힣]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _take_by_popularity(
        self, items: list[RankedGame], limit: int
    ) -> list[RankedGame]:
        if limit <= 0:
            return []
        ordered = sorted(
            items,
            key=lambda item: (item.pop_score, item.rec_score, item.game_id),
            reverse=True,
        )
        return ordered[:limit]

    def _count_liked(self, items: list[RankedGame]) -> int:
        return sum(1 for item in items if item.is_liked)

    def _liked_cap(self, total_limit: int) -> int:
        return max(1, int(total_limit * MATCH_RESULT_LIKED_RATIO_CAP))

    def _to_vector(self, raw: object) -> list[float]:
        if raw is None:
            return []
        if isinstance(raw, (str, bytes, bytearray)):
            return []
        if not isinstance(raw, IterableABC):
            return []

        out: list[float] = []
        for value in raw:
            try:
                out.append(float(value))
            except TypeError:
                return []
            except ValueError:
                return []
        return out

    def _result_sim_vector(self, vec: list[float] | None) -> list[float]:
        if not vec:
            return []

        out = list(vec[:MATCH_RESULT_SIM_VECTOR_DIM])
        if len(out) < MATCH_RESULT_SIM_VECTOR_DIM:
            out.extend([0.0] * (MATCH_RESULT_SIM_VECTOR_DIM - len(out)))
        return out

    def _result_split_similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0

        # dim1~8: 장르축
        genre_sim = self._cosine_similarity(a[:8], b[:8])
        # dim9~13: 분위기/성향축
        mood_sim = self._cosine_similarity(a[8:13], b[8:13])

        weight_sum = MATCH_RESULT_SIM_GENRE_WEIGHT + MATCH_RESULT_SIM_MOOD_WEIGHT
        if weight_sum <= 0.0:
            return 0.0

        sim = (
            (genre_sim * MATCH_RESULT_SIM_GENRE_WEIGHT)
            + (mood_sim * MATCH_RESULT_SIM_MOOD_WEIGHT)
        ) / weight_sum

        return max(-1.0, min(1.0, sim))

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        sim = dot / (norm_a * norm_b)
        return max(-1.0, min(1.0, sim))

    def _to_pop_score(self, rating: object) -> float:
        value = self._safe_float(rating, default=-1.0)
        if value < 0.0:
            return MATCH_RESULT_POP_DEFAULT
        return max(0.0, min(1.0, value / 100.0))

    def _to_rec_score(self, release_date: object) -> float:
        if not isinstance(release_date, datetime):
            return 0.0

        dt = release_date
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        release_ts = int(dt.timestamp())
        if release_ts <= 0:
            return 0.0

        now_ts = int(time.time())
        window_sec = MATCH_RESULT_RECENCY_WINDOW_DAYS * 24 * 60 * 60
        window_start = now_ts - window_sec

        rec = (release_ts - window_start) / float(window_sec)
        return max(0.0, min(1.0, rec))

    def _normalize_rating(self, rating: object) -> float:
        value = self._safe_float(rating, default=0.0)
        return round(max(0.0, min(100.0, value)), 2)

    def _compose_final_score(
        self,
        *,
        sim: float,
        pop: float,
        rec: float,
        like_bonus: float,
        dislike_penalty: float,
    ) -> float:
        # 정규화 기준:
        # MATCH_RESULT_SCORE_NORMALIZER(1.095) = 양의 최대 가중치 합
        # = 0.75(sim) + 0.15*1.10(pop) + 0.10(rec) + 0.08(like_bonus)
        pop_weight = MATCH_RESULT_WEIGHT_POP * MATCH_RESULT_POP_BOOST

        final_raw = (
                (sim * MATCH_RESULT_WEIGHT_SIM)
                + (pop * pop_weight)
                + (rec * MATCH_RESULT_WEIGHT_REC)
                + (like_bonus * MATCH_RESULT_WEIGHT_LIKE_BONUS)
                - (dislike_penalty * MATCH_RESULT_WEIGHT_DISLIKE_PENALTY)
        )
        return round(max(0.0, final_raw) / MATCH_RESULT_SCORE_NORMALIZER, 6)

    def _safe_float(self, value: object, *, default: float) -> float:
        if value is None or isinstance(value, bool):
            return default
        if isinstance(value, (int, float, str, bytes, bytearray)):
            try:
                return float(value)
            except TypeError:
                return default
            except ValueError:
                return default
        return default

    def _to_thumbnail_url(self, cover: object) -> str:
        if not isinstance(cover, str) or not cover.strip():
            return ""

        value = cover.strip()
        if value.startswith("//"):
            value = f"https:{value}"

        if value.startswith("http://") or value.startswith("https://"):
            return value.replace("t_thumb", "t_1080p")

        # cover가 igdb image id 형태로 저장된 경우
        if "/" not in value:
            return f"https://images.igdb.com/igdb/image/upload/t_1080p/{value}.jpg"

        return value.replace("t_thumb", "t_1080p")
