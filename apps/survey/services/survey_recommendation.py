import base64
import json
import re
import time
from typing import Any

import requests
from django.conf import settings
from django.db.models import (
    BigIntegerField,
    F,
    FloatField,
    IntegerField,
    Q,
    QuerySet,
    Value,
    Window,
)
from django.db.models.functions import Coalesce, RowNumber
from django.utils import timezone
from pgvector.django import CosineDistance
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from apps.core.igdb import IGDB
from apps.games.models import Game
from apps.survey.constants import (
    SURVEY_ALLOWED_GAME_CATEGORIES,
    SURVEY_RECOMMENDATION_MAX_RESULTS,
    SURVEY_RECOMMENDATION_MIN_RELEASE_YEAR,
)
from apps.survey.models import SurveyChatbotSession, SurveyGameVector
from apps.users.models import UserLikeBookmark


class SurveyRecommendationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "추천 데이터 조회 중 외부 서비스 오류가 발생했습니다."
    default_code = "survey_recommendation_unavailable"


class SurveyRecommendationNotReady(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "설문 추천 결과를 찾을 수 없습니다."
    default_code = "survey_recommendation_not_ready"


class SurveyGameEmbeddingService:
    # 우리 서버 DB(game_list)에 이미 저장된 게임 중, 설문 추천용 후보만 고릅니다.
    # 별도 외부 게임 목록 호출 없이 DB에 있는 일부 게임만 임베딩합니다.
    CANDIDATE_ONLY_FIELDS = (
        "game_id",
        "name",
        "slug",
        "summary",
        "storyline",
        "category",
        "status",
        "first_release_date",
        "rating",
        "rating_count",
        "aggregated_rating",
        "aggregated_rating_count",
        "total_rating",
        "total_rating_count",
        "genres",
        "themes",
        "keywords",
        "game_modes",
        "player_perspectives",
        "cover",
        "collection",
        "parent_game",
        "is_ban",
    )
    SUMMARY_MAX_LENGTH = 1200
    STORYLINE_MAX_LENGTH = 700
    LIST_TEXT_MAX_ITEMS = 12
    LIST_TEXT_MAX_LENGTH = 240
    EMBEDDING_MAX_TEXT_LENGTH = 2600
    EMBEDDING_MAX_ATTEMPTS = 3
    EMBEDDING_BACKOFF_SECONDS = 1.0

    def get_candidate_games(
        self,
        *,
        offset: int = 0,
        limit: int | None = 100,
        only_missing: bool = True,
    ) -> QuerySet[Game]:
        representative_ids = self.get_series_representative_game_ids()
        queryset = (
            Game.objects.filter(game_id__in=representative_ids)
            .only(*self.CANDIDATE_ONLY_FIELDS)
            .order_by("game_id")
        )
        if only_missing:
            queryset = queryset.exclude(
                game_id__in=SurveyGameVector.objects.values_list("game_id", flat=True)
            )

        if limit is None:
            return queryset[offset:]
        return queryset[offset : offset + limit]

    def get_series_representative_game_ids(self) -> QuerySet[Any]:
        return (
            Game.objects.filter(self.build_candidate_filter())
            .annotate(
                rating_data_count=self.build_rating_data_count_expression(),
                series_key=Coalesce(
                    "collection",
                    "game_id",
                    output_field=BigIntegerField(),
                ),
                representative_score=Coalesce(
                    "total_rating",
                    "aggregated_rating",
                    "rating",
                    Value(0.0),
                    output_field=FloatField(),
                ),
                representative_rating_count=Coalesce(
                    "total_rating_count",
                    "aggregated_rating_count",
                    "rating_count",
                    Value(0),
                    output_field=IntegerField(),
                ),
                series_rank=Window(
                    expression=RowNumber(),
                    partition_by=[F("series_key")],
                    order_by=[
                        F("representative_score").desc(),
                        F("representative_rating_count").desc(),
                        F("game_id").desc(),
                    ],
                ),
            )
            .filter(rating_data_count__gte=5, series_rank=1)
            .values_list("game_id", flat=True)
        )

    def build_rating_data_count_expression(self) -> Any:
        return (
            Coalesce("rating_count", Value(0), output_field=IntegerField())
            + Coalesce("aggregated_rating_count", Value(0), output_field=IntegerField())
            + Coalesce("total_rating_count", Value(0), output_field=IntegerField())
        )

    # DB에서 미리 걸러낼 수 있는 조건은 최대한 queryset에서 처리합니다.
    def build_candidate_filter(self) -> Q:
        return (
            Q(is_ban=False)
            & (
                Q(category__isnull=True)
                | Q(category__in=SURVEY_ALLOWED_GAME_CATEGORIES)
            )
            & (Q(status__isnull=True) | Q(status=0))
            & Q(parent_game__isnull=True)
            & Q(first_release_date__isnull=False)
            & Q(first_release_date__year__gte=SURVEY_RECOMMENDATION_MIN_RELEASE_YEAR)
            & Q(cover__isnull=False)
            & ~Q(cover="")
            & Q(genres__isnull=False)
            & ~Q(genres=[])
            & (
                (Q(summary__isnull=False) & ~Q(summary=""))
                | (Q(storyline__isnull=False) & ~Q(storyline=""))
            )
        )

    def is_game_eligible(self, game: Game) -> bool:
        return (
            self.is_category_eligible(game)
            and self.is_release_status_eligible(game)
            and self.is_quality_eligible(game)
            and self.has_required_fields(game)
            and self.is_release_date_eligible(game)
        )

    def is_category_eligible(self, game: Game) -> bool:
        if game.category is None:
            return True
        return int(game.category) in SURVEY_ALLOWED_GAME_CATEGORIES

    def is_release_status_eligible(self, game: Game) -> bool:
        if game.status is None:
            return True
        return int(game.status) == 0

    def is_quality_eligible(self, game: Game) -> bool:
        rating_data_count = sum(
            count or 0
            for count in (
                game.rating_count,
                game.aggregated_rating_count,
                game.total_rating_count,
            )
        )
        return rating_data_count >= 5

    def has_required_fields(self, game: Game) -> bool:
        has_genres = bool(game.genres)
        has_release_date = game.first_release_date is not None
        has_cover = bool((game.cover or "").strip())
        has_description = bool(
            (game.summary or "").strip() or (game.storyline or "").strip()
        )
        return has_genres and has_release_date and has_cover and has_description

    def is_release_date_eligible(self, game: Game) -> bool:
        if game.first_release_date is None:
            return False
        return game.first_release_date.year >= SURVEY_RECOMMENDATION_MIN_RELEASE_YEAR

    # 중요도가 높은 설명 필드를 더 길게 반영하고 전체 길이를 제한합니다.
    def build_embedding_source(self, game: Game) -> str:
        parts = [
            f"제목: {game.name}",
            f"장르: {', '.join(self.extract_genre_names(game.genres))}",
        ]

        if game.summary:
            parts.append(
                f"핵심 설명: {self.truncate_text(game.summary, self.SUMMARY_MAX_LENGTH)}"
            )
        if game.storyline:
            parts.append(
                f"스토리 맥락: {self.truncate_text(game.storyline, self.STORYLINE_MAX_LENGTH)}"
            )
        if game.themes:
            parts.append(f"테마: {self.stringify_value_list(game.themes)}")
        if game.keywords:
            parts.append(f"키워드: {self.stringify_value_list(game.keywords)}")
        if game.game_modes:
            parts.append(f"게임모드: {self.stringify_value_list(game.game_modes)}")
        if game.player_perspectives:
            parts.append(f"시점: {self.stringify_value_list(game.player_perspectives)}")

        return self.truncate_text(
            "\n".join(part for part in parts if part.strip()),
            self.EMBEDDING_MAX_TEXT_LENGTH,
        )

    def stringify_value_list(self, values: object) -> str:
        if not isinstance(values, list):
            return ""
        normalized: list[str] = []
        for value in values[: self.LIST_TEXT_MAX_ITEMS]:
            if isinstance(value, dict):
                name = value.get("name")
                if name:
                    normalized.append(str(name))
                    continue
                value_id = value.get("id")
                if value_id:
                    normalized.append(str(value_id))
                    continue
            normalized.append(str(value))
        return self.truncate_text(
            ", ".join(item for item in normalized if item),
            self.LIST_TEXT_MAX_LENGTH,
        )

    def truncate_text(self, value: str, max_length: int) -> str:
        normalized = " ".join(value.split())
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"

    def extract_genre_names(self, genres: object) -> list[str]:
        if not isinstance(genres, list):
            return []

        names: list[str] = []
        for genre in genres:
            genre_id = None
            if isinstance(genre, dict):
                genre_id = genre.get("id")
            else:
                genre_id = genre

            if genre_id is None:
                continue

            name = IGDB.GENRE_NAME_MAP.get(int(genre_id))
            if name and name not in names:
                names.append(name)

        return names

    # 임베딩 API 실패 시 네트워크/일시 오류를 고려해 최대 3회 재시도합니다.
    def generate_game_embedding(self, source_text: str) -> list[float]:
        api_key = settings.SURVEY_CHATBOT_GEMINI_API_KEY
        if not api_key:
            raise SurveyRecommendationUnavailable()

        url = (
            f"{settings.SURVEY_CHATBOT_GEMINI_BASE_URL}/v1beta/models/"
            f"{settings.SURVEY_EMBEDDING_MODEL}:embedContent"
        )
        payload = {
            "model": f"models/{settings.SURVEY_EMBEDDING_MODEL}",
            "content": {"parts": [{"text": source_text}]},
            "taskType": "RETRIEVAL_DOCUMENT",
            "outputDimensionality": 1536,
        }

        last_error: Exception | None = None
        for attempt in range(self.EMBEDDING_MAX_ATTEMPTS):
            try:
                response = requests.post(
                    url=url,
                    params={"key": api_key},
                    json=payload,
                    timeout=settings.SURVEY_EMBEDDING_TIMEOUT,
                )
                response.raise_for_status()
                values = response.json()["embedding"]["values"]
                if not isinstance(values, list) or not values:
                    raise ValueError("embedding values are empty")
                return [float(value) for value in values]
            except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
                last_error = exc
                if attempt < self.EMBEDDING_MAX_ATTEMPTS - 1:
                    time.sleep(self.EMBEDDING_BACKOFF_SECONDS * (2**attempt))
                    continue

        raise SurveyRecommendationUnavailable() from last_error

    def sync_embeddings(
        self,
        *,
        offset: int = 0,
        limit: int | None = 100,
        only_missing: bool = True,
    ) -> dict[str, int]:
        queryset = self.get_candidate_games(
            offset=offset,
            limit=limit,
            only_missing=only_missing,
        )
        processed = 0
        failed = 0
        for game in queryset.iterator():
            try:
                embedding = self.generate_game_embedding(
                    self.build_embedding_source(game)
                )
                SurveyGameVector.objects.update_or_create(
                    game_id=game.game_id,
                    defaults={"embedding": embedding},
                )
                processed += 1
            except SurveyRecommendationUnavailable:
                failed += 1

        return {"count": processed, "failed": failed}


class SurveyRecommendationService:
    CURSOR_DISTANCE_KEY = "s"
    CURSOR_GAME_ID_KEY = "g"
    RERANK_POOL_SIZE = 100
    SIMILARITY_WEIGHT = 0.55
    PRIMARY_SLOT_WEIGHT = 0.20
    GENRE_WEIGHT = 0.10
    RECENCY_WEIGHT = 0.10
    RATING_WEIGHT = 0.05
    NEGATIVE_SLOT_PENALTY = 0.20
    NEGATIVE_MARKERS = (
        "싫",
        "피로",
        "선호하지",
        "못 느",
        "재미를 못",
        "안 좋아",
        "별로",
    )
    PREFERENCE_SLOT_RULES: dict[str, dict[str, tuple[str, ...]]] = {
        "solo": {
            "user": ("혼자", "솔로", "싱글", "혼자서"),
            "game": ("혼자", "솔로", "싱글", "single", "single-player"),
        },
        "coop": {
            "user": ("협동", "협력", "팀원", "친구와", "함께"),
            "game": ("협동", "협력", "co-op", "coop", "cooperative", "multiplayer"),
        },
        "competition": {
            "user": ("경쟁", "대결", "다른 플레이어", "pvp", "실력을 겨루"),
            "game": ("경쟁", "대결", "pvp", "versus", "competitive", "multiplayer"),
        },
        "pve": {
            "user": ("pve", "ai", "적들", "몬스터", "보스"),
            "game": ("pve", "ai", "enemy", "enemies", "monster", "boss", "보스"),
        },
        "combat": {
            "user": ("전투", "액션", "싸우", "적", "물리치", "공격", "보스"),
            "game": (
                "전투",
                "액션",
                "격투",
                "슈팅",
                "combat",
                "action",
                "fight",
                "battle",
                "enemy",
                "boss",
            ),
        },
        "story": {
            "user": ("스토리", "이야기", "서사", "세계관"),
            "game": ("스토리", "이야기", "서사", "story", "narrative", "world"),
        },
        "exploration": {
            "user": ("탐험", "탐색", "발견", "모험"),
            "game": ("탐험", "어드벤처", "exploration", "explore", "adventure"),
        },
        "puzzle": {
            "user": ("퍼즐", "수수께끼", "단서", "문제"),
            "game": ("퍼즐", "puzzle", "riddle", "clue"),
        },
        "strategy": {
            "user": ("전략", "전술", "계획", "판단"),
            "game": ("전략", "전술", "strategy", "tactical", "tactics"),
        },
        "growth": {
            "user": ("성장", "레벨", "장비", "빌드", "강해"),
            "game": ("성장", "레벨", "장비", "빌드", "rpg", "level", "build", "gear"),
        },
    }

    def __init__(self) -> None:
        self.embedding_service = SurveyGameEmbeddingService()

    def get_recommendations(
        self,
        *,
        user: Any,
        session_id: str,
        cursor: str | None,
        page_size: int,
    ) -> dict[str, Any]:
        # 추천 비교 대상은 survey_game_vector에 임베딩이 저장된 게임만 사용합니다.
        session = self.get_closed_session(user=user, session_id=session_id)
        user_vector = self.get_user_vector(user)
        excluded_keywords = self.get_excluded_keywords(session)
        excluded_game_ids = self.collect_excluded_game_ids(user, excluded_keywords)

        vector_queryset = (
            SurveyGameVector.objects.filter(embedding__isnull=False)
            .exclude(game_id__in=excluded_game_ids)
            .annotate(distance=CosineDistance("embedding", user_vector))
            .order_by("distance", "game_id")
        )

        ranked_items = self.rank_recommendation_items(
            items=list(vector_queryset[: self.RERANK_POOL_SIZE]),
            survey_answer=getattr(session.results, "survey_answer", "") or "",
        )[:SURVEY_RECOMMENDATION_MAX_RESULTS]
        total_count = len(ranked_items)
        cursor_position = self.decode_cursor(cursor)
        if cursor_position:
            cursor_score, cursor_game_id = cursor_position
            ranked_items = [
                item
                for item in ranked_items
                if self.is_after_cursor(item, cursor_score, cursor_game_id)
            ]

        page = ranked_items[: page_size + 1]
        has_next = len(page) > page_size
        page = page[:page_size]
        next_cursor = self.encode_cursor(page[-1]) if has_next and page else None

        games = Game.objects.filter(game_id__in=[item.game_id for item in page]).only(
            "game_id",
            "name",
            "genres",
            "cover",
            "total_rating",
            "aggregated_rating",
            "rating",
        )
        game_map = {int(game.game_id): game for game in games}
        liked_ids = set(
            UserLikeBookmark.objects.filter(
                user=user,
                game_id__in=[item.game_id for item in page],
            ).values_list("game_id", flat=True)
        )

        results = []
        for item in page:
            game = game_map.get(int(item.game_id))
            if not game:
                continue
            results.append(
                {
                    "game_id": int(game.game_id),
                    "title": game.name,
                    "genres": self.embedding_service.extract_genre_names(game.genres),
                    "thumbnail_url": self.build_cover_url(game.cover),
                    "rating": self.normalize_rating(game),
                    "is_liked": int(game.game_id) in liked_ids,
                }
            )

        return {
            "user_id": int(user.pk),
            "count": total_count,
            "next": next_cursor,
            "results": results,
        }

    def is_after_cursor(
        self,
        item: SurveyGameVector,
        cursor_score: float,
        cursor_game_id: int,
    ) -> bool:
        item_score = self.get_cursor_score(item)
        return item_score < cursor_score or (
            item_score == cursor_score and int(item.game_id) > cursor_game_id
        )

    def encode_cursor(self, item: SurveyGameVector) -> str:
        payload = {
            self.CURSOR_DISTANCE_KEY: self.get_cursor_score(item),
            self.CURSOR_GAME_ID_KEY: int(item.game_id),
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()
        return encoded.rstrip("=")

    def decode_cursor(self, cursor: str | None) -> tuple[float, int] | None:
        if not cursor:
            return None

        try:
            padded_cursor = cursor + ("=" * (-len(cursor) % 4))
            payload = json.loads(base64.urlsafe_b64decode(padded_cursor).decode())
            distance = float(payload[self.CURSOR_DISTANCE_KEY])
            game_id = int(payload[self.CURSOR_GAME_ID_KEY])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SurveyRecommendationUnavailable(
                "유효하지 않은 cursor입니다."
            ) from exc

        return distance, game_id

    def rank_recommendation_items(
        self,
        items: list[SurveyGameVector],
        survey_answer: str = "",
    ) -> list[SurveyGameVector]:
        if not items:
            return []

        preference_profile = self.build_preference_profile(survey_answer)
        game_map = {
            int(game.game_id): game
            for game in Game.objects.filter(
                game_id__in=[int(item.game_id) for item in items]
            ).only(
                "game_id",
                "first_release_date",
                "total_rating",
                "aggregated_rating",
                "rating",
                "name",
                "genres",
                "summary",
                "storyline",
                "themes",
                "keywords",
                "game_modes",
                "player_perspectives",
            )
        }
        for item in items:
            game = game_map.get(int(item.game_id))
            item.recommendation_score = self.calculate_recommendation_score(
                distance=float(item.distance),
                game=game,
                preference_profile=preference_profile,
            )

        return sorted(
            items,
            key=lambda item: (-self.get_cursor_score(item), int(item.game_id)),
        )

    def calculate_recommendation_score(
        self,
        *,
        distance: float,
        game: Game | None,
        preference_profile: dict[str, set[str]] | None = None,
    ) -> float:
        similarity_score = max(0.0, min(1.0, 1.0 - distance))
        primary_slot_score = self.calculate_primary_slot_score(
            game=game,
            preference_profile=preference_profile,
        )
        genre_score = self.calculate_genre_score(
            game=game,
            preference_profile=preference_profile,
        )
        rating_score = self.calculate_rating_score(game)
        recency_score = self.calculate_recency_score(game)
        negative_penalty = self.calculate_negative_slot_penalty(
            game=game,
            preference_profile=preference_profile,
        )
        return (
            self.SIMILARITY_WEIGHT * similarity_score
            + self.PRIMARY_SLOT_WEIGHT * primary_slot_score
            + self.GENRE_WEIGHT * genre_score
            + self.RECENCY_WEIGHT * recency_score
            + self.RATING_WEIGHT * rating_score
            - self.NEGATIVE_SLOT_PENALTY * negative_penalty
        )

    def build_preference_profile(self, survey_answer: str) -> dict[str, set[str]]:
        normalized_answer = self.normalize_match_text(survey_answer)
        positive_slots = {
            slot
            for slot, rules in self.PREFERENCE_SLOT_RULES.items()
            if self.contains_any(normalized_answer, rules["user"])
            and not self.contains_near_negative(normalized_answer, rules["user"])
        }
        negative_slots = {
            slot
            for slot, rules in self.PREFERENCE_SLOT_RULES.items()
            if self.contains_near_negative(normalized_answer, rules["user"])
        }
        preferred_genres = {
            genre_name
            for genre_name in IGDB.GENRE_NAME_MAP.values()
            if genre_name.lower() in normalized_answer
        }
        return {
            "positive_slots": positive_slots,
            "negative_slots": negative_slots,
            "preferred_genres": preferred_genres,
        }

    def calculate_primary_slot_score(
        self,
        *,
        game: Game | None,
        preference_profile: dict[str, set[str]] | None,
    ) -> float:
        if not game or not preference_profile:
            return 0.0

        positive_slots = preference_profile["positive_slots"]
        if not positive_slots:
            return 0.0

        game_slots = self.detect_game_slots(game)
        return len(positive_slots & game_slots) / len(positive_slots)

    def calculate_negative_slot_penalty(
        self,
        *,
        game: Game | None,
        preference_profile: dict[str, set[str]] | None,
    ) -> float:
        if not game or not preference_profile:
            return 0.0

        negative_slots = preference_profile["negative_slots"]
        if not negative_slots:
            return 0.0

        game_slots = self.detect_game_slots(game)
        return len(negative_slots & game_slots) / len(negative_slots)

    def calculate_genre_score(
        self,
        *,
        game: Game | None,
        preference_profile: dict[str, set[str]] | None,
    ) -> float:
        if not game or not preference_profile:
            return 0.0

        preferred_genres = preference_profile["preferred_genres"]
        if not preferred_genres:
            return 0.0

        game_genres = set(self.embedding_service.extract_genre_names(game.genres))
        return len(preferred_genres & game_genres) / len(preferred_genres)

    def detect_game_slots(self, game: Game) -> set[str]:
        game_text = self.build_game_match_text(game)
        return {
            slot
            for slot, rules in self.PREFERENCE_SLOT_RULES.items()
            if self.contains_any(game_text, rules["game"])
        }

    def build_game_match_text(self, game: Game) -> str:
        parts = [
            game.name or "",
            " ".join(self.embedding_service.extract_genre_names(game.genres)),
            game.summary or "",
            game.storyline or "",
            self.embedding_service.stringify_value_list(game.themes),
            self.embedding_service.stringify_value_list(game.keywords),
            self.embedding_service.stringify_value_list(game.game_modes),
            self.embedding_service.stringify_value_list(game.player_perspectives),
        ]
        return self.normalize_match_text(" ".join(parts))

    def normalize_match_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.lower()).strip()

    def contains_any(self, text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword.lower() in text for keyword in keywords)

    def contains_near_negative(self, text: str, keywords: tuple[str, ...]) -> bool:
        for keyword in keywords:
            keyword_pattern = re.escape(keyword.lower())
            for match in re.finditer(keyword_pattern, text):
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                window = text[start:end]
                if self.contains_any(window, self.NEGATIVE_MARKERS):
                    return True
        return False

    def calculate_rating_score(self, game: Game | None) -> float:
        if not game:
            return 0.0

        rating = self.normalize_rating(game)
        if rating is None:
            return 0.0
        return max(0.0, min(1.0, rating / 100.0))

    def calculate_recency_score(self, game: Game | None) -> float:
        if not game or not game.first_release_date:
            return 0.0

        release_year = game.first_release_date.year
        current_year = timezone.now().year
        year_range = current_year - SURVEY_RECOMMENDATION_MIN_RELEASE_YEAR
        if year_range <= 0:
            return 0.0
        recency = (release_year - SURVEY_RECOMMENDATION_MIN_RELEASE_YEAR) / year_range
        return max(0.0, min(1.0, recency))

    def get_cursor_score(self, item: SurveyGameVector) -> float:
        score = getattr(item, "recommendation_score", None)
        if score is not None:
            return float(score)
        distance = getattr(item, "distance", 0.0)
        return float(distance or 0.0)

    def get_closed_session(self, *, user: Any, session_id: str) -> SurveyChatbotSession:
        try:
            session = SurveyChatbotSession.objects.select_related("results").get(
                id=session_id,
                user=user,
            )
        except SurveyChatbotSession.DoesNotExist as exc:
            raise NotFound("설문 추천 결과를 찾을 수 없습니다.") from exc

        if session.status != "closed":
            raise SurveyRecommendationNotReady()
        return session

    def get_user_vector(self, user: Any) -> list[float]:
        preference = getattr(user, "preference", None)
        if not preference or preference.survey_vector is None:
            raise SurveyRecommendationNotReady()
        return list(preference.survey_vector)

    def get_excluded_keywords(self, session: SurveyChatbotSession) -> list[str]:
        if not hasattr(session, "results") or not session.results:
            return []

        raw_keywords = session.results.excluded_keywords or "[]"
        try:
            data = json.loads(raw_keywords)
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        return [str(item).strip() for item in data if str(item).strip()]

    # 제외 키워드는 한 번의 매칭 쿼리로 모으고, 시리즈 확장은 후속 쿼리로 처리합니다.
    def collect_excluded_game_ids(self, user: Any, keywords: list[str]) -> set[int]:
        liked_ids = set(
            UserLikeBookmark.objects.filter(user=user).values_list("game_id", flat=True)
        )
        excluded_ids = set(int(game_id) for game_id in liked_ids)
        if not keywords:
            return excluded_ids

        keyword_query = Q()
        for keyword in keywords:
            keyword_query |= Q(name__icontains=keyword) | Q(slug__icontains=keyword)

        matched_games = list(
            Game.objects.filter(keyword_query)
            .only("game_id", "collection", "parent_game", "franchises")
            .distinct()
        )
        if not matched_games:
            return excluded_ids

        excluded_ids.update(int(game.game_id) for game in matched_games)

        collection_ids = {
            int(game.collection) for game in matched_games if game.collection
        }
        if collection_ids:
            excluded_ids.update(
                int(game_id)
                for game_id in Game.objects.filter(
                    collection__in=collection_ids
                ).values_list("game_id", flat=True)
            )

        parent_ids = {
            int(parent_id)
            for parent_id in {
                *(game.parent_game for game in matched_games if game.parent_game),
                *(game.game_id for game in matched_games),
            }
        }
        if parent_ids:
            excluded_ids.update(
                int(game_id)
                for game_id in Game.objects.filter(game_id__in=parent_ids).values_list(
                    "game_id", flat=True
                )
            )
            excluded_ids.update(
                int(game_id)
                for game_id in Game.objects.filter(
                    parent_game__in=parent_ids
                ).values_list("game_id", flat=True)
            )

        franchise_query = Q()
        for game in matched_games:
            if isinstance(game.franchises, list):
                for franchise in game.franchises:
                    if franchise:
                        franchise_query |= Q(franchises__contains=[franchise])
        if franchise_query:
            excluded_ids.update(
                int(game_id)
                for game_id in Game.objects.filter(franchise_query).values_list(
                    "game_id", flat=True
                )
            )

        return excluded_ids

    def build_cover_url(self, cover: str | None) -> str | None:
        if not cover:
            return None
        if str(cover).startswith("http://") or str(cover).startswith("https://"):
            return str(cover)
        return f"https://images.igdb.com/igdb/image/upload/t_cover_big/{cover}.jpg"

    def normalize_rating(self, game: Game) -> float | None:
        rating = game.total_rating or game.aggregated_rating or game.rating
        if rating is None:
            return None
        return round(float(rating), 1)
