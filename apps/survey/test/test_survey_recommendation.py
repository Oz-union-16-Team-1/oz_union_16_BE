import json
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.survey.choices import SurveyStatusChoices
from apps.survey.models import SurveyChatbotSession, SurveyGameVector, SurveyResults
from apps.survey.serializers.survey_recommendation import (
    SurveyRecommendationQuerySerializer,
)
from apps.survey.services.survey_recommendation import (
    SurveyGameEmbeddingService,
    SurveyRecommendationNotReady,
    SurveyRecommendationService,
    SurveyRecommendationUnavailable,
)
from apps.users.models import User, UserLikeBookmark, UserPreference


def create_user(**kwargs) -> User:
    defaults = {
        "login_id": f"survey_{uuid.uuid4().hex[:8]}",
        "password": "testpassword123",
        "name": "설문유저",
        "nickname": f"survey_nick_{uuid.uuid4().hex[:8]}",
        "gender": "M",
    }
    defaults.update(kwargs)
    password = defaults.pop("password")
    user = User(**defaults)
    user.set_password(password)
    user.save()
    return user


def create_game(**kwargs) -> Game:
    defaults = {
        "game_id": kwargs.pop("game_id", int(uuid.uuid4().int % 100000)),
        "name": kwargs.pop("name", "테스트 게임"),
        "slug": kwargs.pop("slug", "test-game"),
        "summary": kwargs.pop("summary", "전투와 성장 요소가 있는 게임"),
        "storyline": kwargs.pop("storyline", "어두운 분위기의 스토리"),
        "category": kwargs.pop("category", 0),
        "status": kwargs.pop("status", 0),
        "first_release_date": kwargs.pop(
            "first_release_date", datetime(2020, 1, 1, tzinfo=timezone.utc)
        ),
        "rating": kwargs.pop("rating", 80.0),
        "rating_count": kwargs.pop("rating_count", 30),
        "aggregated_rating": kwargs.pop("aggregated_rating", 85.0),
        "aggregated_rating_count": kwargs.pop("aggregated_rating_count", 10),
        "total_rating": kwargs.pop("total_rating", 82.0),
        "genres": kwargs.pop("genres", [12, 4]),
        "themes": kwargs.pop("themes", [19]),
        "keywords": kwargs.pop("keywords", [25]),
        "game_modes": kwargs.pop("game_modes", [1]),
        "player_perspectives": kwargs.pop("player_perspectives", [3]),
        "cover": kwargs.pop("cover", "coverid"),
        "collection": kwargs.pop("collection", None),
        "franchises": kwargs.pop("franchises", []),
        "parent_game": kwargs.pop("parent_game", None),
        "is_ban": kwargs.pop("is_ban", False),
    }
    defaults.update(kwargs)
    return Game.objects.create(**defaults)


class SurveyRecommendationAPITest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user = create_user()
        self.session = SurveyChatbotSession.objects.create(
            user=self.user,
            status=SurveyStatusChoices.CLOSED,
        )
        SurveyResults.objects.create(
            chatbot_session=self.session,
            user=self.user,
            survey_answer="격투 액션과 전략적 반격 플레이를 좋아합니다.",
            excluded_keywords=json.dumps(["철권"], ensure_ascii=False),
        )
        UserPreference.objects.create(
            user=self.user,
            survey_vector=[1.0] + ([0.0] * 1535),
        )
        self.url = reverse(
            "survey-recommendation",
            kwargs={"session_id": self.session.id},
        )

    def authenticate(self) -> None:
        self.client.force_authenticate(user=self.user)

    def test_authentication_required(self) -> None:
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_recommendations_returns_cursor_paginated_results(self) -> None:
        self.authenticate()
        included_game = create_game(game_id=101, name="세키로", slug="sekiro")
        second_game = create_game(game_id=102, name="인왕", slug="nioh")
        excluded_series_game = create_game(
            game_id=103,
            name="철권 8",
            slug="tekken-8",
            collection=1000,
        )
        create_game(
            game_id=104,
            name="철권 7",
            slug="tekken-7",
            collection=1000,
        )
        liked_game = create_game(game_id=105, name="스트리트 파이터 6", slug="sf6")
        UserLikeBookmark.objects.create(user=self.user, game_id=liked_game.game_id)

        SurveyGameVector.objects.create(
            game_id=included_game.game_id,
            embedding=[1.0] + ([0.0] * 1535),
        )
        SurveyGameVector.objects.create(
            game_id=second_game.game_id,
            embedding=[0.7, 0.7] + ([0.0] * 1534),
        )
        SurveyGameVector.objects.create(
            game_id=excluded_series_game.game_id,
            embedding=[1.0] + ([0.0] * 1535),
        )
        SurveyGameVector.objects.create(
            game_id=liked_game.game_id,
            embedding=[1.0] + ([0.0] * 1535),
        )

        first_response = self.client.get(self.url, {"page_size": 1})

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data["user_id"], self.user.pk)
        self.assertEqual(first_response.data["count"], 2)
        self.assertEqual(first_response.data["next"], "1")
        self.assertEqual(len(first_response.data["results"]), 1)
        self.assertEqual(
            first_response.data["results"][0]["game_id"], included_game.game_id
        )
        self.assertEqual(first_response.data["results"][0]["title"], "세키로")
        self.assertEqual(
            first_response.data["results"][0]["genres"], ["카드/보드", "슈팅"]
        )
        self.assertIn("coverid.jpg", first_response.data["results"][0]["thumbnail_url"])
        self.assertFalse(first_response.data["results"][0]["is_liked"])

        second_response = self.client.get(
            self.url,
            {"page_size": 1, "cursor": first_response.data["next"]},
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(second_response.data["next"])
        self.assertEqual(
            second_response.data["results"][0]["game_id"], second_game.game_id
        )

    def test_open_session_returns_conflict(self) -> None:
        self.authenticate()
        self.session.status = SurveyStatusChoices.IN_PROGRESS
        self.session.save(update_fields=["status"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


class SurveyRecommendationServiceTest(TestCase):
    def setUp(self) -> None:
        self.user = create_user()
        self.session = SurveyChatbotSession.objects.create(
            user=self.user,
            status=SurveyStatusChoices.CLOSED,
        )
        SurveyResults.objects.create(
            chatbot_session=self.session,
            user=self.user,
            survey_answer="어두운 분위기의 액션 RPG 선호",
            excluded_keywords=json.dumps(["철권"], ensure_ascii=False),
        )
        UserPreference.objects.create(user=self.user, survey_vector=[1.0] * 1536)
        self.service = SurveyRecommendationService()
        self.embedding_service = SurveyGameEmbeddingService()

    def test_get_user_vector_raises_when_missing(self) -> None:
        other_user = create_user()
        with self.assertRaises(SurveyRecommendationNotReady):
            self.service.get_user_vector(other_user)

    def test_collect_excluded_game_ids_excludes_series_and_likes(self) -> None:
        matched = create_game(
            game_id=201,
            name="철권 8",
            slug="tekken-8",
            collection=2000,
            franchises=[3000],
        )
        series = create_game(
            game_id=202,
            name="철권 7",
            slug="tekken-7",
            collection=2000,
            franchises=[3000],
        )
        child = create_game(
            game_id=203,
            name="철권 태그",
            slug="tekken-tag",
            parent_game=matched.game_id,
        )
        liked = create_game(game_id=204, name="좋아요 게임", slug="liked-game")
        UserLikeBookmark.objects.create(user=self.user, game_id=liked.game_id)

        excluded_ids = self.service.collect_excluded_game_ids(self.user, ["철권"])

        self.assertIn(matched.game_id, excluded_ids)
        self.assertIn(series.game_id, excluded_ids)
        self.assertIn(child.game_id, excluded_ids)
        self.assertIn(liked.game_id, excluded_ids)

    def test_build_cover_url_and_normalize_rating(self) -> None:
        game = create_game(game_id=205, total_rating=91.27, cover="abc123")
        self.assertIn("abc123.jpg", self.service.build_cover_url(game.cover))
        self.assertIsNone(self.service.build_cover_url(None))
        self.assertEqual(self.service.normalize_rating(game), 91.3)
        game.total_rating = None
        game.aggregated_rating = None
        game.rating = None
        self.assertIsNone(self.service.normalize_rating(game))

    def test_embedding_source_and_genre_names(self) -> None:
        game = create_game(
            game_id=206,
            name="다크소울",
            genres=[12, 4],
            keywords=[25],
            themes=[19],
        )

        source_text = self.embedding_service.build_embedding_source(game)

        self.assertIn("제목: 다크소울", source_text)
        self.assertIn("장르: 카드/보드, 슈팅", source_text)
        self.assertIn("핵심 설명:", source_text)

    def test_is_game_eligible(self) -> None:
        good_game = create_game(game_id=207)
        bad_game = create_game(
            game_id=208,
            rating=None,
            rating_count=None,
            aggregated_rating=None,
            aggregated_rating_count=None,
        )

        self.assertTrue(self.embedding_service.is_game_eligible(good_game))
        self.assertFalse(self.embedding_service.is_game_eligible(bad_game))

    def test_query_serializer_validates_cursor_and_default_page_size(self) -> None:
        serializer = SurveyRecommendationQuerySerializer(data={})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["page_size"], 5)

        invalid = SurveyRecommendationQuerySerializer(data={"cursor": "abc"})
        self.assertFalse(invalid.is_valid())
        self.assertIn("cursor", invalid.errors)

    def test_category_release_and_required_field_branches(self) -> None:
        no_category_game = create_game(game_id=210, category=None, status=None)
        self.assertTrue(self.embedding_service.is_category_eligible(no_category_game))
        self.assertTrue(
            self.embedding_service.is_release_status_eligible(no_category_game)
        )

        invalid_category_game = create_game(game_id=211, category=5)
        invalid_status_game = create_game(game_id=212, status=2)
        self.assertFalse(
            self.embedding_service.is_category_eligible(invalid_category_game)
        )
        self.assertFalse(
            self.embedding_service.is_release_status_eligible(invalid_status_game)
        )

        no_genres = create_game(game_id=213, genres=[])
        no_cover = create_game(game_id=214, cover="")
        no_description = create_game(game_id=215, summary=" ", storyline=" ")
        self.assertFalse(self.embedding_service.has_required_fields(no_genres))
        self.assertFalse(self.embedding_service.has_required_fields(no_cover))
        self.assertFalse(self.embedding_service.has_required_fields(no_description))

    def test_release_date_and_quality_branches(self) -> None:
        no_release_date = create_game(game_id=216, first_release_date=None)
        old_release_date = create_game(
            game_id=217,
            first_release_date=datetime(1999, 1, 1, tzinfo=timezone.utc),
        )
        critic_only_game = create_game(
            game_id=218,
            rating=None,
            rating_count=None,
            aggregated_rating=70.0,
            aggregated_rating_count=5,
        )
        critic_fail_game = create_game(
            game_id=219,
            rating=80.0,
            rating_count=30,
            aggregated_rating=55.0,
            aggregated_rating_count=5,
        )

        self.assertFalse(
            self.embedding_service.is_release_date_eligible(no_release_date)
        )
        self.assertFalse(
            self.embedding_service.is_release_date_eligible(old_release_date)
        )
        self.assertTrue(self.embedding_service.is_quality_eligible(critic_only_game))
        self.assertFalse(self.embedding_service.is_quality_eligible(critic_fail_game))

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY="test-key")
    @patch("apps.survey.services.survey_recommendation.requests.post")
    def test_generate_game_embedding(self, mock_post) -> None:
        mock_response = mock_post.return_value
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"embedding": {"values": [0.1, 0.2, 0.3]}}

        embedding = self.embedding_service.generate_game_embedding("테스트 텍스트")

        self.assertEqual(embedding, [0.1, 0.2, 0.3])
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["taskType"], "RETRIEVAL_DOCUMENT")

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY="test-key")
    @patch("apps.survey.services.survey_recommendation.requests.post")
    @patch("apps.survey.services.survey_recommendation.time.sleep")
    def test_generate_game_embedding_raises_on_failure(
        self, mock_sleep, mock_post
    ) -> None:
        mock_post.side_effect = requests.RequestException

        with self.assertRaises(SurveyRecommendationUnavailable):
            self.embedding_service.generate_game_embedding("테스트 텍스트")
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY="")
    def test_generate_game_embedding_raises_without_api_key(self) -> None:
        with self.assertRaises(SurveyRecommendationUnavailable):
            self.embedding_service.generate_game_embedding("테스트 텍스트")

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY="test-key")
    @patch("apps.survey.services.survey_recommendation.requests.post")
    @patch("apps.survey.services.survey_recommendation.time.sleep")
    def test_generate_game_embedding_raises_on_empty_values(
        self, mock_sleep, mock_post
    ) -> None:
        mock_response = mock_post.return_value
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"embedding": {"values": []}}

        with self.assertRaises(SurveyRecommendationUnavailable):
            self.embedding_service.generate_game_embedding("테스트 텍스트")
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @override_settings(SURVEY_CHATBOT_GEMINI_API_KEY="test-key")
    @patch("apps.survey.services.survey_recommendation.time.sleep")
    @patch("apps.survey.services.survey_recommendation.requests.post")
    def test_generate_game_embedding_retries_then_succeeds(
        self, mock_post, mock_sleep
    ) -> None:
        success_response = Mock()
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {"embedding": {"values": [0.1, 0.2]}}
        mock_post.side_effect = [requests.RequestException, success_response]

        embedding = self.embedding_service.generate_game_embedding("테스트 텍스트")

        self.assertEqual(embedding, [0.1, 0.2])
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch(
        "apps.survey.services.survey_recommendation.SurveyGameEmbeddingService.generate_game_embedding"
    )
    def test_sync_embeddings(self, mock_generate_game_embedding) -> None:
        game = create_game(game_id=209)
        mock_generate_game_embedding.return_value = [0.1] * 1536

        result = self.embedding_service.sync_embeddings(limit=10)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertTrue(SurveyGameVector.objects.filter(game_id=game.game_id).exists())

    @patch(
        "apps.survey.services.survey_recommendation.SurveyGameEmbeddingService.generate_game_embedding"
    )
    def test_sync_embeddings_continues_when_some_games_fail(
        self, mock_generate_game_embedding
    ) -> None:
        create_game(game_id=241, name="실패 게임", slug="fail-game")
        success_game = create_game(game_id=242, name="성공 게임", slug="success-game")
        mock_generate_game_embedding.side_effect = [
            SurveyRecommendationUnavailable(),
            [0.1] * 1536,
        ]

        result = self.embedding_service.sync_embeddings(limit=10)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertTrue(
            SurveyGameVector.objects.filter(game_id=success_game.game_id).exists()
        )
        self.assertFalse(SurveyGameVector.objects.filter(game_id=241).exists())

    def test_get_candidate_games_uses_db_filters(self) -> None:
        invalid_category = create_game(game_id=234, category=5)
        eligible_game = create_game(game_id=235, category=0)

        queryset = self.embedding_service.get_candidate_games(limit=10)

        self.assertNotIn(
            invalid_category.game_id,
            queryset.values_list("game_id", flat=True),
        )
        self.assertEqual(
            list(queryset.values_list("game_id", flat=True)),
            [eligible_game.game_id],
        )

    def test_stringify_and_extract_helpers_cover_edge_cases(self) -> None:
        self.assertEqual(self.embedding_service.stringify_value_list("invalid"), "")
        self.assertEqual(
            self.embedding_service.stringify_value_list(
                [{"name": "보스전"}, {"id": 99}, "직접값"]
            ),
            "보스전, 99, 직접값",
        )
        self.assertEqual(self.embedding_service.extract_genre_names("invalid"), [])
        self.assertEqual(
            self.embedding_service.extract_genre_names(
                [{"id": 12}, {"id": 12}, {"id": 999}, None]
            ),
            ["카드/보드"],
        )

    def test_recommendations_only_compare_embedded_games(self) -> None:
        embedded_game = create_game(game_id=239, name="임베딩된 게임", slug="embedded")
        non_embedded_game = create_game(
            game_id=240,
            name="임베딩 안 된 게임",
            slug="not-embedded",
        )
        SurveyGameVector.objects.create(
            game_id=embedded_game.game_id,
            embedding=[1.0] + ([0.0] * 1535),
        )

        result = self.service.get_recommendations(
            user=self.user,
            session_id=str(self.session.id),
            cursor=None,
            page_size=10,
        )

        result_ids = [item["game_id"] for item in result["results"]]
        self.assertIn(embedded_game.game_id, result_ids)
        self.assertNotIn(non_embedded_game.game_id, result_ids)

    def test_build_embedding_source_truncates_long_text(self) -> None:
        game = create_game(
            game_id=236,
            summary="요약 " * 1000,
            storyline="스토리 " * 1000,
            keywords=[{"name": f"키워드{i}"} for i in range(30)],
        )

        source_text = self.embedding_service.build_embedding_source(game)

        self.assertLessEqual(
            len(source_text), self.embedding_service.EMBEDDING_MAX_TEXT_LENGTH
        )
        self.assertIn("핵심 설명:", source_text)

    def test_get_closed_session_and_excluded_keyword_branches(self) -> None:
        with self.assertRaisesMessage(Exception, "설문 챗봇 세션을 찾을 수 없습니다."):
            self.service.get_closed_session(
                user=self.user, session_id=str(uuid.uuid4())
            )
        liked = create_game(game_id=238, name="좋아요만 제외", slug="liked-only")
        UserLikeBookmark.objects.create(user=self.user, game_id=liked.game_id)
        self.assertEqual(
            self.service.collect_excluded_game_ids(self.user, []),
            {liked.game_id},
        )

        no_result_user = create_user()
        no_result_session = SurveyChatbotSession.objects.create(
            user=no_result_user,
            status=SurveyStatusChoices.CLOSED,
        )
        self.assertEqual(self.service.get_excluded_keywords(no_result_session), [])

        invalid_json_user = create_user()
        invalid_json_session = SurveyChatbotSession.objects.create(
            user=invalid_json_user,
            status=SurveyStatusChoices.CLOSED,
        )
        SurveyResults.objects.create(
            chatbot_session=invalid_json_session,
            user=invalid_json_user,
            survey_answer="테스트",
            excluded_keywords="invalid-json",
        )
        self.assertEqual(self.service.get_excluded_keywords(invalid_json_session), [])

        not_list_user = create_user()
        not_list_session = SurveyChatbotSession.objects.create(
            user=not_list_user,
            status=SurveyStatusChoices.CLOSED,
        )
        SurveyResults.objects.create(
            chatbot_session=not_list_session,
            user=not_list_user,
            survey_answer="테스트",
            excluded_keywords='{"name": "철권"}',
        )
        self.assertEqual(self.service.get_excluded_keywords(not_list_session), [])

    def test_recommendations_skip_missing_game_and_cover_variants(self) -> None:
        SurveyGameVector.objects.create(
            game_id=999999, embedding=[1.0] + ([0.0] * 1535)
        )
        http_cover_game = create_game(
            game_id=220,
            name="HTTP 커버 게임",
            cover="https://cdn.example.com/cover.jpg",
            total_rating=None,
            aggregated_rating=None,
            rating=77.49,
        )
        SurveyGameVector.objects.create(
            game_id=http_cover_game.game_id,
            embedding=[1.0] + ([0.0] * 1535),
        )

        result = self.service.get_recommendations(
            user=self.user,
            session_id=str(self.session.id),
            cursor=None,
            page_size=5,
        )

        self.assertEqual(result["count"], 2)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(
            result["results"][0]["thumbnail_url"], "https://cdn.example.com/cover.jpg"
        )
        self.assertEqual(result["results"][0]["rating"], 77.5)
