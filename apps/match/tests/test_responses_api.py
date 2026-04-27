from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.match.models import MatchGamePreference, MatchGameRating
from apps.match.services.responses_submit import (
    MatchResponsesGameNotFoundError,
    MatchResponsesSubmitService,
    MatchResponsesValidationError,
)
from apps.users.models import UserLikeBookmark, UserPreference


class MatchResponsesFixtureMixin:
    @staticmethod
    def _vector(seed: int) -> list[float]:
        return [(((seed + idx * 5) % 29) - 14) / 14.0 for idx in range(14)]

    @classmethod
    def _create_game(
        cls,
        *,
        game_id: int,
        with_vector: bool = True,
        is_ban: bool = False,
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
            rating=82.0,
            rating_count=50,
            aggregated_rating=80.0,
            aggregated_rating_count=5,
            total_rating=82.0,
            total_rating_count=50,
            game_modes=[1, 2],
            player_perspectives=[2],
            themes=[1],
            genres=[2],
            videos=[{"video_id": "abc"}],
            game_type=0,
            is_ban=is_ban,
        )
        if with_vector:
            MatchGamePreference.objects.create(
                game_id=game,
                game_preference_vector=cls._vector(game_id),
            )
        return game


class MatchResponsesSubmitServiceTest(MatchResponsesFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            login_id="responses_service_user",
            password="Pass1234!",
            name="테스터",
            nickname="responses_service_tester",
            gender="M",
        )
        cls.game1 = cls._create_game(game_id=9101, with_vector=True)
        cls.game2 = cls._create_game(game_id=9102, with_vector=True)
        cls.game_no_vector = cls._create_game(game_id=9103, with_vector=False)

    def setUp(self) -> None:
        self.service = MatchResponsesSubmitService()

    def test_submit_success_keeps_like_when_is_liked_omitted(self):
        UserLikeBookmark.objects.create(user=self.user, game_id=self.game1.game_id)

        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id, self.game2.game_id],
        ):
            result = self.service.submit(
                user_id=self.user.id,
                genre_id=2,
                retry_no=0,
                match_result=[
                    {"game_id": self.game1.game_id, "rating": 5},  # is_liked 미전달
                    {"game_id": self.game2.game_id, "rating": 3, "is_liked": False},
                ],
            )

        self.assertEqual(result["user_id"], self.user.id)
        self.assertEqual(len(result["match_result"]), 2)

        result_map = {row["game_id"]: row for row in result["match_result"]}
        self.assertTrue(result_map[self.game1.game_id]["is_liked"])
        self.assertFalse(result_map[self.game2.game_id]["is_liked"])

        self.assertTrue(
            UserLikeBookmark.objects.filter(
                user=self.user,
                game_id=self.game1.game_id,
            ).exists()
        )
        self.assertEqual(
            MatchGameRating.objects.filter(user=self.user).count(),
            2,
        )

        pref = UserPreference.objects.get(user=self.user)
        self.assertEqual(len(pref.match_vector), 14)

    def test_submit_duplicate_game_id_last_write_wins(self):
        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id],
        ):
            result = self.service.submit(
                user_id=self.user.id,
                genre_id=2,
                retry_no=0,
                match_result=[
                    {"game_id": self.game1.game_id, "rating": 1, "is_liked": False},
                    {"game_id": self.game1.game_id, "rating": 4, "is_liked": True},
                ],
            )

        self.assertEqual(len(result["match_result"]), 1)
        self.assertEqual(result["match_result"][0]["rating"], 4)
        self.assertTrue(result["match_result"][0]["is_liked"])

        row = MatchGameRating.objects.get(user=self.user, game_id=self.game1.game_id)
        self.assertEqual(row.star_rating, 4)
        self.assertEqual(row.rating_count, 1)

    def test_submit_rerating_updates_effective_rating_and_count(self):
        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id],
        ):
            self.service.submit(
                user_id=self.user.id,
                genre_id=2,
                retry_no=0,
                match_result=[{"game_id": self.game1.game_id, "rating": 5}],
            )
            self.service.submit(
                user_id=self.user.id,
                genre_id=2,
                retry_no=0,
                match_result=[{"game_id": self.game1.game_id, "rating": 3}],
            )

        row = MatchGameRating.objects.get(user=self.user, game_id=self.game1.game_id)
        self.assertEqual(row.star_rating, 3)
        self.assertEqual(row.rating_count, 2)
        self.assertAlmostEqual(float(row.effective_rating), 4.0, places=2)

    def test_submit_rejects_non_integer_inputs_strictly(self):
        bad_payloads = [
            [{"game_id": self.game1.game_id, "rating": 4.9}],
            [{"game_id": self.game1.game_id, "rating": "4.0"}],
            [{"game_id": "9101.3", "rating": 4}],
            [{"game_id": True, "rating": 4}],
            [{"game_id": self.game1.game_id, "rating": True}],
        ]

        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id],
        ):
            for payload in bad_payloads:
                with self.subTest(payload=payload):
                    with self.assertRaises(MatchResponsesValidationError):
                        self.service.submit(
                            user_id=self.user.id,
                            genre_id=2,
                            retry_no=0,
                            match_result=payload,
                        )

    def test_submit_rejects_candidate_mismatch(self):
        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id],
        ):
            with self.assertRaises(MatchResponsesValidationError):
                self.service.submit(
                    user_id=self.user.id,
                    genre_id=2,
                    retry_no=0,
                    match_result=[{"game_id": self.game2.game_id, "rating": 4}],
                )

    def test_submit_raises_not_found_when_game_missing(self):
        missing_game_id = 999999

        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[missing_game_id],
        ):
            with self.assertRaises(MatchResponsesGameNotFoundError):
                self.service.submit(
                    user_id=self.user.id,
                    genre_id=2,
                    retry_no=0,
                    match_result=[{"game_id": missing_game_id, "rating": 4}],
                )

    def test_submit_skips_vector_update_when_game_vector_missing(self):
        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game_no_vector.game_id],
        ):
            with self.assertLogs(
                "apps.match.services.responses_submit",
                level="WARNING",
            ) as logs:
                result = self.service.submit(
                    user_id=self.user.id,
                    genre_id=2,
                    retry_no=0,
                    match_result=[{"game_id": self.game_no_vector.game_id, "rating": 4}],
                )

        self.assertEqual(result["match_result"][0]["game_id"], self.game_no_vector.game_id)
        self.assertIn("vector missing", "\n".join(logs.output))
        self.assertTrue(
            MatchGameRating.objects.filter(
                user=self.user,
                game_id=self.game_no_vector.game_id,
            ).exists()
        )


class MatchResponsesAPITest(MatchResponsesFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("match-responses")
        cls.user = get_user_model().objects.create_user(
            login_id="responses_api_user",
            password="Pass1234!",
            name="테스터",
            nickname="responses_api_tester",
            gender="M",
        )
        cls.game1 = cls._create_game(game_id=9201, with_vector=True)
        cls.game2 = cls._create_game(game_id=9202, with_vector=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_post_responses_success_returns_200(self):
        payload = {
            "genre_id": 2,
            "retry_no": 0,
            "match_result": [
                {"game_id": self.game1.game_id, "rating": 5, "is_liked": True},
                {"game_id": self.game2.game_id, "rating": 3},
            ],
        }

        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id, self.game2.game_id],
        ):
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user_id"], self.user.id)
        self.assertEqual(len(response.data["match_result"]), 2)

    def test_post_responses_duplicate_game_last_write_wins(self):
        payload = {
            "genre_id": 2,
            "retry_no": 0,
            "match_result": [
                {"game_id": self.game1.game_id, "rating": 1, "is_liked": False},
                {"game_id": self.game1.game_id, "rating": 4, "is_liked": True},
            ],
        }

        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id],
        ):
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["match_result"]), 1)
        self.assertEqual(response.data["match_result"][0]["rating"], 4)
        self.assertTrue(response.data["match_result"][0]["is_liked"])

    def test_post_responses_unauthorized_returns_401(self):
        anonymous_client = APIClient()
        response = anonymous_client.post(
            self.url,
            {"genre_id": 2, "retry_no": 0, "match_result": []},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error_detail", response.data)

    def test_post_responses_invalid_params_returns_400(self):
        response = self.client.post(
            self.url,
            {
                "genre_id": 9,
                "retry_no": -1,
                "match_result": [{"game_id": self.game1.game_id, "rating": 6}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("genre_id", response.data["error_detail"])

    def test_post_responses_candidate_mismatch_returns_400(self):
        payload = {
            "genre_id": 2,
            "retry_no": 0,
            "match_result": [{"game_id": self.game2.game_id, "rating": 4}],
        }

        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id],
        ):
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["error_detail"],
            "후보 세트에 없는 game_id가 포함되어 있습니다.",
        )

    def test_post_responses_not_found_returns_404(self):
        missing_game_id = 999999
        payload = {
            "genre_id": 2,
            "retry_no": 0,
            "match_result": [{"game_id": missing_game_id, "rating": 4}],
        }

        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[missing_game_id],
        ):
            response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error_detail"], "해당 게임을 찾을 수 없습니다.")
