from __future__ import annotations

import logging
import math
from collections.abc import Iterable as IterableABC
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.games.models import Game
from apps.match.constants import (
    MATCH_GENRE_BASELINE,
    MATCH_GENRE_BUDGET_SOFT_LIMIT,
    MATCH_GENRE_BUDGET_STRENGTH,
    MATCH_GENRE_MAX_CAP,
    MATCH_GENRE_NEAR_CAP_THRESHOLD,
    MATCH_GENRE_NORM_ALPHA,
    MATCH_GENRE_SATURATION_DECAY,
    MATCH_RESPONSE_LOW_RATING_LAMBDA,
    MATCH_RESPONSE_MAX_STAR,
    MATCH_RESPONSE_MIN_ALPHA,
    MATCH_RESPONSE_MIN_STAR,
    MATCH_VECTOR_DIM,
)
from apps.match.models import (
    MatchCandidateRetryState,
    MatchGamePreference,
    MatchGameRating,
)
from apps.match.services.candidates_selector import MatchCandidatesSelectorService
from apps.users.models import UserLikeBookmark, UserPreference

logger = logging.getLogger(__name__)


class MatchResponsesValidationError(ValueError):
    pass


class MatchResponsesGameNotFoundError(LookupError):
    def __init__(self, missing_game_ids: list[int]) -> None:
        super().__init__("해당 게임을 찾을 수 없습니다.")
        self.missing_game_ids = missing_game_ids


@dataclass(frozen=True)
class NormalizedResponse:
    game_id: int
    rating: int
    is_liked: bool | None  # None이면 기존 상태 유지


class MatchResponsesSubmitService:
    def submit(
        self,
        *,
        user_id: int,
        genre_id: int,
        retry_no: int,
        match_result: list[dict[str, Any]],
        candidate_date: date | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_and_dedupe(match_result)
        game_ids = [item.game_id for item in normalized]
        base_day = candidate_date or timezone.localdate()

        self._ensure_games_exist(game_ids)
        game_vectors = self._load_game_vectors(game_ids)
        missing_vector_ids: list[int] = []

        with transaction.atomic():
            retry_state = self._lock_retry_state(
                user_id=user_id,
                genre_id=genre_id,
                candidate_date=base_day,
            )

            expected_retry_no = max(0, int(retry_state.last_completed_retry_no) + 1)
            if int(retry_no) != expected_retry_no:
                raise MatchResponsesValidationError("유효하지 않은 retry_no 입니다.")

            self._validate_submitted_games_are_candidates(
                user_id=user_id,
                genre_id=genre_id,
                retry_no=retry_no,
                candidate_date=base_day,
                submitted_game_ids=game_ids,
            )

            pref, _ = UserPreference.objects.select_for_update().get_or_create(
                user_id=user_id
            )
            user_vector = self._to_user_vector(pref.match_vector)

            for item in normalized:
                effective_rating = self._upsert_rating_row(
                    user_id=user_id,
                    game_id=item.game_id,
                    rating=item.rating,
                )

                game_vector = game_vectors.get(item.game_id)
                if game_vector is not None:
                    weight = self._rating_to_weight(effective_rating)
                    self._accumulate(user_vector, game_vector, weight)

                    if item.rating == MATCH_RESPONSE_MIN_STAR:
                        self._accumulate(
                            user_vector,
                            game_vector,
                            -MATCH_RESPONSE_LOW_RATING_LAMBDA,
                        )
                else:
                    missing_vector_ids.append(item.game_id)

                self._sync_like(
                    user_id=user_id,
                    game_id=item.game_id,
                    is_liked=item.is_liked,
                )

            pref.match_vector = self._soft_clip(user_vector)
            pref.save(update_fields=["match_vector", "updated_at"])

            retry_state.last_completed_retry_no = int(retry_no)
            retry_state.save(update_fields=["last_completed_retry_no", "updated_at"])

        if missing_vector_ids:
            logger.warning(
                "[MATCH][RESPONSES] vector missing -> skipped vector update user_id=%s game_ids=%s",
                user_id,
                sorted(set(missing_vector_ids)),
            )

        liked_ids = set(
            UserLikeBookmark.objects.filter(
                user_id=user_id,
                game_id__in=game_ids,
            ).values_list("game_id", flat=True)
        )

        return {
            "match_result": [
                {
                    "game_id": item.game_id,
                    "rating": item.rating,
                    "is_liked": item.game_id in liked_ids,
                }
                for item in normalized
            ],
        }

    def _normalize_and_dedupe(
        self,
        match_result: list[dict[str, Any]],
    ) -> list[NormalizedResponse]:
        if not match_result:
            raise MatchResponsesValidationError(
                "match_result는 최소 1개 이상이어야 합니다."
            )

        by_game_id: dict[int, NormalizedResponse] = {}

        for row in match_result:
            if not isinstance(row, dict):
                raise MatchResponsesValidationError(
                    "match_result 형식이 올바르지 않습니다."
                )

            game_id = self._parse_int_strict(row.get("game_id"), field_name="game_id")
            rating = self._parse_int_strict(row.get("rating"), field_name="rating")

            if game_id <= 0:
                raise MatchResponsesValidationError("game_id는 1 이상이어야 합니다.")
            if not (MATCH_RESPONSE_MIN_STAR <= rating <= MATCH_RESPONSE_MAX_STAR):
                raise MatchResponsesValidationError("1~5 사이 정수여야 합니다.")

            raw_is_liked = row.get("is_liked") if "is_liked" in row else None
            if raw_is_liked is not None and not isinstance(raw_is_liked, bool):
                raise MatchResponsesValidationError("is_liked는 boolean이어야 합니다.")

            # 동일 요청 내 중복 game_id는 마지막 값 우선
            if game_id in by_game_id:
                del by_game_id[game_id]

            by_game_id[game_id] = NormalizedResponse(
                game_id=game_id,
                rating=rating,
                is_liked=raw_is_liked,
            )

        return list(by_game_id.values())

    def _parse_int_strict(self, value: Any, *, field_name: str) -> int:
        if isinstance(value, bool):
            raise MatchResponsesValidationError(f"{field_name}는 정수여야 합니다.")

        if isinstance(value, int):
            return value

        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise MatchResponsesValidationError(f"{field_name}는 정수여야 합니다.")
            if text.isdigit():
                return int(text)
            if text.startswith("-") and text[1:].isdigit():
                return int(text)

        raise MatchResponsesValidationError(f"{field_name}는 정수여야 합니다.")

    def _validate_submitted_games_are_candidates(
        self,
        *,
        user_id: int,
        genre_id: int,
        retry_no: int,
        candidate_date: date | None,
        submitted_game_ids: list[int],
    ) -> None:
        base_day = candidate_date or timezone.localdate()
        submitted_set = set(submitted_game_ids)

        expected_ids = set(
            MatchCandidatesSelectorService().select_game_ids(
                user_id=user_id,
                api_genre_id=genre_id,
                retry_no=retry_no,
                today=base_day,
                liked_game_ids=self._locked_liked_ids_for_validation(
                    user_id=user_id,
                    submitted_game_ids=submitted_set,
                ),
            )
        )

        invalid = sorted(submitted_set - expected_ids)
        if invalid:
            raise MatchResponsesValidationError(
                "후보 세트에 없는 game_id가 포함되어 있습니다."
            )

    def _locked_liked_ids_for_validation(
        self,
        *,
        user_id: int,
        submitted_game_ids: set[int],
    ) -> set[int]:
        """
        제출 검증 시점에 평가중 토글된 liked 변화가
        후보 재계산 결과를 흔들지 않도록 제출 대상 game_id는 제외한다.
        """
        current_liked_ids = set(
            UserLikeBookmark.objects.filter(user_id=user_id).values_list(
                "game_id",
                flat=True,
            )
        )
        return current_liked_ids - submitted_game_ids

    def _lock_retry_state(
        self,
        *,
        user_id: int,
        genre_id: int,
        candidate_date: date,
    ) -> MatchCandidateRetryState:
        state, _ = MatchCandidateRetryState.objects.select_for_update().get_or_create(
            user_id=user_id,
            api_genre_id=genre_id,
            candidate_date=candidate_date,
            defaults={"last_completed_retry_no": -1},
        )
        return state

    def _ensure_games_exist(self, game_ids: list[int]) -> None:
        existing = set(
            Game.objects.filter(game_id__in=game_ids, is_ban=False).values_list(
                "game_id", flat=True
            )
        )
        missing = sorted(set(game_ids) - existing)
        if missing:
            raise MatchResponsesGameNotFoundError(missing_game_ids=missing)

    def _load_game_vectors(self, game_ids: list[int]) -> dict[int, list[float]]:
        rows = MatchGamePreference.objects.filter(game_id_id__in=game_ids).values_list(
            "game_id_id",
            "game_preference_vector",
        )

        out: dict[int, list[float]] = {}
        for game_id, raw_vector in rows:
            vector = self._to_game_vector(raw_vector)
            if vector is not None:
                out[int(game_id)] = vector
        return out

    def _upsert_rating_row(self, *, user_id: int, game_id: int, rating: int) -> float:
        try:
            row, created = MatchGameRating.objects.get_or_create(
                user_id=user_id,
                game_id=game_id,
                defaults={
                    "star_rating": rating,
                    "effective_rating": Decimal(f"{float(rating):.2f}"),
                    "rating_count": 1,
                },
            )
        except IntegrityError:
            row = MatchGameRating.objects.get(user_id=user_id, game_id=game_id)
            created = False

        row = MatchGameRating.objects.select_for_update().get(pk=row.pk)

        if created:
            return float(row.effective_rating)

        n = int(row.rating_count)
        alpha = max(1.0 / float(n + 1), MATCH_RESPONSE_MIN_ALPHA)
        prev_effective = float(row.effective_rating)
        effective = prev_effective * (1.0 - alpha) + float(rating) * alpha

        row.star_rating = rating
        row.effective_rating = Decimal(f"{effective:.2f}")
        row.rating_count = n + 1
        row.save(
            update_fields=[
                "star_rating",
                "effective_rating",
                "rating_count",
                "updated_at",
            ]
        )
        return float(row.effective_rating)

    def _sync_like(self, *, user_id: int, game_id: int, is_liked: bool | None) -> None:
        # 미전달이면 기존 상태 유지
        if is_liked is None:
            return

        if is_liked:
            UserLikeBookmark.objects.get_or_create(user_id=user_id, game_id=game_id)
            return

        UserLikeBookmark.objects.filter(user_id=user_id, game_id=game_id).delete()

    def _rating_to_weight(self, effective_rating: float) -> float:
        x = max(
            float(MATCH_RESPONSE_MIN_STAR),
            min(float(MATCH_RESPONSE_MAX_STAR), float(effective_rating)),
        )
        points = (
            (1.0, -1.0),
            (2.0, -0.5),
            (3.0, 0.0),
            (4.0, 0.5),
            (5.0, 1.0),
        )

        for idx in range(1, len(points)):
            x0, y0 = points[idx - 1]
            x1, y1 = points[idx]
            if x <= x1:
                ratio = (x - x0) / (x1 - x0)
                return y0 + ratio * (y1 - y0)

        return 1.0

    def _accumulate(
        self, target: list[float], source: list[float], scale: float
    ) -> None:
        for idx in range(MATCH_VECTOR_DIM):
            delta = source[idx] * scale

            # dim1~8(장르축): near-cap 구간에서 양(+)증분만 감쇠
            if idx < 8 and delta > 0.0:
                delta *= self._genre_positive_damping(target[idx])

            target[idx] += delta

        self._postprocess_genre_axes(target)

    def _genre_positive_damping(self, current_value: float) -> float:
        threshold = float(MATCH_GENRE_NEAR_CAP_THRESHOLD)
        cap = float(MATCH_GENRE_MAX_CAP)

        if current_value < threshold:
            return 1.0
        if cap <= threshold:
            return 1.0

        ratio = (current_value - threshold) / (cap - threshold)
        ratio = max(0.0, min(1.0, ratio))

        # cap에 가까울수록 증분 축소
        return max(0.0, 1.0 - (float(MATCH_GENRE_SATURATION_DECAY) * ratio))

    def _postprocess_genre_axes(self, vector: list[float]) -> None:
        # dim1~8만 대상. dim9~14는 절대 건드리지 않음.
        self._apply_soft_genre_budget(vector)
        self._apply_min_genre_normalization(vector)

    def _apply_soft_genre_budget(self, vector: list[float]) -> None:
        genre = vector[:8]
        total = sum(genre)
        soft_limit = float(MATCH_GENRE_BUDGET_SOFT_LIMIT)
        strength = float(MATCH_GENRE_BUDGET_STRENGTH)

        if total <= soft_limit or total <= 0.0 or strength <= 0.0:
            return

        overflow = total - soft_limit
        shrink = overflow * strength

        # 초과분만 비례 축소 (약한 제약)
        for i in range(8):
            ratio = genre[i] / total if total > 0.0 else 0.0
            vector[i] -= shrink * ratio

    def _apply_min_genre_normalization(self, vector: list[float]) -> None:
        baseline = float(MATCH_GENRE_BASELINE)
        alpha = float(MATCH_GENRE_NORM_ALPHA)

        if alpha <= 0.0:
            return

        # baseline(중립값)으로 아주 약하게 수축
        for i in range(8):
            vector[i] = vector[i] + (baseline - vector[i]) * alpha

    def _soft_clip(self, vector: list[float]) -> list[float]:
        out: list[float] = []
        for idx, value in enumerate(vector):
            t = math.tanh(value)
            if idx < 8:
                out.append((t + 1.0) / 2.0)  # dim1~8: [0,1]
            else:
                out.append(t)  # dim9~14: [-1,1]
        return out

    def _to_user_vector(self, raw: object) -> list[float]:
        if raw is None:
            return [0.0] * MATCH_VECTOR_DIM
        if isinstance(raw, (str, bytes, bytearray)):
            return [0.0] * MATCH_VECTOR_DIM
        if not isinstance(raw, IterableABC):
            return [0.0] * MATCH_VECTOR_DIM

        result: list[float] = []
        for value in raw:
            try:
                result.append(float(value))
            except TypeError:
                return [0.0] * MATCH_VECTOR_DIM
            except ValueError:
                return [0.0] * MATCH_VECTOR_DIM

        if len(result) < MATCH_VECTOR_DIM:
            result.extend([0.0] * (MATCH_VECTOR_DIM - len(result)))
        return result[:MATCH_VECTOR_DIM]

    def _to_game_vector(self, raw: object) -> list[float] | None:
        # game vector는 누락을 숨기지 않기 위해 None 허용
        if raw is None:
            return None
        if isinstance(raw, (str, bytes, bytearray)):
            return None
        if not isinstance(raw, IterableABC):
            return None

        result: list[float] = []
        for value in raw:
            try:
                result.append(float(value))
            except TypeError:
                return None
            except ValueError:
                return None

        if len(result) < MATCH_VECTOR_DIM:
            result.extend([0.0] * (MATCH_VECTOR_DIM - len(result)))
        return result[:MATCH_VECTOR_DIM]
