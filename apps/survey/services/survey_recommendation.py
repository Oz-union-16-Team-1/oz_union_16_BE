import base64
import json
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
from pgvector.django import CosineDistance
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from apps.core.igdb import IGDB
from apps.games.models import Game
from apps.survey.constants import (
    SURVEY_ALLOWED_GAME_CATEGORIES,
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
        "franchises",
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
        limit: int = 100,
        only_missing: bool = True,
    ) -> QuerySet[Game]:
        # 시리즈 대표작을 먼저 확정한 뒤, 이미 임베딩된 대표작만 제외합니다.
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

        return queryset[offset : offset + limit]

    def get_series_representative_game_ids(self) -> QuerySet[Any]:
        return (
            Game.objects.filter(self.build_candidate_filter())
            .annotate(
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
            .filter(series_rank=1)
            .values_list("game_id", flat=True)
        )

    # DB에서 미리 걸러낼 수 있는 조건은 최대한 queryset에서 처리합니다.
    def build_candidate_filter(self) -> Q:
        user_available_q = Q(rating__isnull=False, rating_count__isnull=False)
        critic_available_q = Q(
            aggregated_rating__isnull=False,
            aggregated_rating_count__isnull=False,
        )
        total_available_q = Q(
            total_rating__isnull=False,
            total_rating_count__isnull=False,
        )
        user_ok_q = Q(rating_count__gte=20, rating__gte=50)
        critic_ok_q = Q(aggregated_rating_count__gte=3, aggregated_rating__gte=60)
        total_ok_q = Q(total_rating_count__gte=20, total_rating__gte=50)
        no_rating_data_q = ~user_available_q & ~critic_available_q & ~total_available_q

        available_rating_q = user_available_q | critic_available_q | total_available_q
        quality_q = no_rating_data_q | (
            available_rating_q
            & (~user_available_q | user_ok_q)
            & (~critic_available_q | critic_ok_q)
            & (~total_available_q | total_ok_q)
        )

        return (
            Q(is_ban=False)
            & (
                Q(category__isnull=True)
                | Q(category__in=SURVEY_ALLOWED_GAME_CATEGORIES)
            )
            & (Q(status__isnull=True) | Q(status=0))
            & Q(parent_game__isnull=True)
            & quality_q
            & Q(first_release_date__isnull=False)
            & Q(first_release_date__year__gte=SURVEY_RECOMMENDATION_MIN_RELEASE_YEAR)
            & Q(genres__isnull=False)
            & ~Q(genres=[])
            & Q(cover__isnull=False)
            & ~Q(cover="")
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
        user_available = game.rating is not None and game.rating_count is not None
        critic_available = (
            game.aggregated_rating is not None
            and game.aggregated_rating_count is not None
        )
        total_available = (
            game.total_rating is not None and game.total_rating_count is not None
        )

        return (
            (not user_available or (game.rating_count >= 20 and game.rating >= 50))
            and (
                not critic_available
                or (game.aggregated_rating_count >= 3 and game.aggregated_rating >= 60)
            )
            and (
                not total_available
                or (game.total_rating_count >= 20 and game.total_rating >= 50)
            )
        )

    def has_required_fields(self, game: Game) -> bool:
        has_genres = bool(game.genres)
        has_release_date = game.first_release_date is not None
        has_cover = bool(game.cover)
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
        limit: int = 100,
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

        total_count = vector_queryset.count()
        cursor_position = self.decode_cursor(cursor)
        if cursor_position:
            cursor_distance, cursor_game_id = cursor_position
            vector_queryset = vector_queryset.filter(
                Q(distance__gt=cursor_distance)
                | Q(distance=cursor_distance, game_id__gt=cursor_game_id)
            )

        page = list(vector_queryset[: page_size + 1])
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

    def encode_cursor(self, item: SurveyGameVector) -> str:
        payload = {
            self.CURSOR_DISTANCE_KEY: float(item.distance),
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
