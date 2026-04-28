from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.match.models import MatchGameGenreMap
from apps.match.services.responses_result_query import (
    MatchResponsesResultDataUnavailable,
    MatchResponsesResultQueryService,
    MatchResponsesResultValidationError,
)
from apps.users.models import UserLikeBookmark


class MatchResponsesResultFixtureMixin:
    @classmethod
    def _create_game(
        cls,
        *,
        game_id: int,
        rating: float,
        genre_ids: list[int],
    ) -> Game:
        game = Game.objects.create(
            game_id=game_id,
            name=f"Game {game_id}",
            slug=f"game-{game_id}",
            summary="summary",
            storyline="",
            category=0,
            status=0,
            first_release_date=datetime(2021, 1, 1, tzinfo=timezone.utc),
            rating=rating,
            rating_count=50,
            aggregated_rating=80.0,
            aggregated_rating_count=5,
            total_rating=rating,
            total_rating_count=50,
            game_modes=[1, 2],
            player_perspectives=[2],
            themes=[1],
            genres=genre_ids,
            videos=[{"video_id": "abc"}],
            game_type=0,
            is_ban=False,
        )
        for genre_id in genre_ids:
            MatchGameGenreMap.objects.create(game_id=game, igdb_genre_id=genre_id)
        return game


class MatchResponsesResultServiceTest(MatchResponsesResultFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            login_id="responses_result_service_user",
            password="Pass1234!",
            name="테스터",
            nickname="responses_result_service_tester",
            gender="M",
        )

        # genre_id=2 -> igdb genre [2, 10]
        cls.games = []
        for idx, rating in enumerate([96, 91, 88, 84, 79, 75, 70], start=1):
            game = cls._create_game(game_id=9300 + idx, rating=rating, genre_ids=[2])
            cls.games.append(game)

        # liked는 기본 fallback 단계에서 제외됨
        cls.liked_game_id = cls.games[0].game_id
        UserLikeBookmark.objects.create(user=cls.user, game_id=cls.liked_game_id)

    def setUp(self) -> None:
        self.service = MatchResponsesResultQueryService()

    def test_get_results_success_with_cursor(self):
        first = self.service.get_results(
            user_id=self.user.id,
            genre_id=2,
            page_size=3,
        )

        self.assertEqual(first["user_id"], self.user.id)
        self.assertEqual(first["count"], 6)  # liked 1개 제외
        self.assertEqual(len(first["results"]), 3)
        self.assertIsNotNone(first["next"])

        first_ids = [row["game_id"] for row in first["results"]]
        self.assertNotIn(self.liked_game_id, first_ids)

        second = self.service.get_results(
            user_id=self.user.id,
            genre_id=2,
            page_size=3,
            cursor=first["next"],
        )
        second_ids = [row["game_id"] for row in second["results"]]

        self.assertEqual(len(set(first_ids).intersection(second_ids)), 0)

    def test_get_results_invalid_cursor_raises_validation_error(self):
        with self.assertRaises(MatchResponsesResultValidationError):
            self.service.get_results(
                user_id=self.user.id,
                genre_id=2,
                page_size=5,
                cursor="not-a-valid-cursor",
            )

    def test_get_results_empty_when_no_genre_candidates(self):
        result = self.service.get_results(
            user_id=self.user.id,
            genre_id=7,
            page_size=5,
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["results"], [])


class MatchResponsesResultAPITest(MatchResponsesResultFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("match-responses-result")
        cls.user = get_user_model().objects.create_user(
            login_id="responses_result_api_user",
            password="Pass1234!",
            name="테스터",
            nickname="responses_result_api_tester",
            gender="M",
        )

        for idx, rating in enumerate([95, 89, 83, 77, 71], start=1):
            cls._create_game(game_id=9400 + idx, rating=rating, genre_ids=[2])

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_responses_result_success_returns_200(self):
        response = self.client.get(
            self.url,
            {"genre_id": 2, "page_size": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user_id", response.data)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("results", response.data)

    def test_get_responses_result_invalid_genre_returns_400(self):
        response = self.client.get(
            self.url,
            {"genre_id": 99, "page_size": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("genre_id", response.data["error_detail"])

    def test_get_responses_result_unauthorized_returns_401(self):
        anonymous_client = APIClient()
        response = anonymous_client.get(self.url, {"genre_id": 2})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error_detail", response.data)

    def test_get_responses_result_not_found_returns_404(self):
        response = self.client.get(
            self.url,
            {"genre_id": 7, "page_size": 5},  # fixture 없음
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_detail"], "매칭 추천 결과를 찾을 수 없습니다.")

    @patch("apps.match.views.rating_responses.MatchResponsesResultQueryService.get_results")
    def test_get_responses_result_service_unavailable_returns_503(self, mock_get_results):
        mock_get_results.side_effect = MatchResponsesResultDataUnavailable()

        response = self.client.get(
            self.url,
            {"genre_id": 2, "page_size": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data["error_detail"],
            "추천 데이터 조회 중 외부 서비스 오류가 발생했습니다.",
        )
