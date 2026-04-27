from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
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

        self.assertEqual(set(result.keys()), {"match_result"})
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
                    match_result=[
                        {"game_id": self.game_no_vector.game_id, "rating": 4}
                    ],
                )

        self.assertEqual(
            result["match_result"][0]["game_id"], self.game_no_vector.game_id
        )
        self.assertIn("vector missing", "\n".join(logs.output))
        self.assertTrue(
            MatchGameRating.objects.filter(
                user=self.user,
                game_id=self.game_no_vector.game_id,
            ).exists()
        )

    def test_submit_rejects_empty_match_result(self):
        with self.assertRaises(MatchResponsesValidationError):
            self.service.submit(
                user_id=self.user.id,
                genre_id=2,
                retry_no=0,
                match_result=[],
            )

    def test_submit_rejects_non_dict_item(self):
        with self.assertRaises(MatchResponsesValidationError):
            self.service.submit(
                user_id=self.user.id,
                genre_id=2,
                retry_no=0,
                match_result=["bad-item"],
            )

    def test_submit_rejects_invalid_value_ranges(self):
        cases = [
            [{"game_id": 0, "rating": 3, "is_liked": False}],
            [{"game_id": self.game1.game_id, "rating": 0, "is_liked": False}],
            [{"game_id": self.game1.game_id, "rating": 6, "is_liked": False}],
            [{"game_id": self.game1.game_id, "rating": 3, "is_liked": "yes"}],
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(MatchResponsesValidationError):
                    self.service.submit(
                        user_id=self.user.id,
                        genre_id=2,
                        retry_no=0,
                        match_result=payload,
                    )

    def test_parse_int_strict_branches(self):
        self.assertEqual(
            self.service._parse_int_strict("12", field_name="game_id"),
            12,
        )
        self.assertEqual(
            self.service._parse_int_strict("-7", field_name="game_id"),
            -7,
        )
        with self.assertRaises(MatchResponsesValidationError):
            self.service._parse_int_strict("", field_name="game_id")
        with self.assertRaises(MatchResponsesValidationError):
            self.service._parse_int_strict("  ", field_name="game_id")
        with self.assertRaises(MatchResponsesValidationError):
            self.service._parse_int_strict("12a", field_name="game_id")

    def test_upsert_rating_row_integrityerror_fallback_path(self):
        existing = MatchGameRating.objects.create(
            user=self.user,
            game_id=self.game1.game_id,
            star_rating=3,
            effective_rating="3.00",
            rating_count=1,
        )

        with (
            patch(
                "apps.match.services.responses_submit.MatchGameRating.objects.get_or_create",
                side_effect=IntegrityError,
            ),
            patch(
                "apps.match.services.responses_submit.MatchGameRating.objects.get",
                return_value=existing,
            ),
        ):
            effective = self.service._upsert_rating_row(
                user_id=self.user.id,
                game_id=self.game1.game_id,
                rating=4,
            )

        self.assertAlmostEqual(effective, 3.5, places=2)

    def test_to_user_vector_branches(self):
        self.assertEqual(self.service._to_user_vector("bad"), [0.0] * 14)
        self.assertEqual(self.service._to_user_vector(None), [0.0] * 14)
        self.assertEqual(self.service._to_user_vector([1, "x"]), [0.0] * 14)

        padded = self.service._to_user_vector([1.0, 2.0])
        self.assertEqual(padded[:2], [1.0, 2.0])
        self.assertEqual(len(padded), 14)

    def test_to_game_vector_branches(self):
        self.assertIsNone(self.service._to_game_vector(None))
        self.assertIsNone(self.service._to_game_vector("bad"))
        self.assertIsNone(self.service._to_game_vector([1, "x"]))

        padded = self.service._to_game_vector([0.1, 0.2])
        self.assertIsNotNone(padded)
        self.assertEqual(padded[:2], [0.1, 0.2])
        self.assertEqual(len(padded), 14)

    def test_submit_rating_one_inverse_branch(self):
        with patch(
            "apps.match.services.responses_submit.MatchCandidatesSelectorService.select_game_ids",
            return_value=[self.game1.game_id],
        ):
            self.service.submit(
                user_id=self.user.id,
                genre_id=2,
                retry_no=0,
                match_result=[{"game_id": self.game1.game_id, "rating": 1}],
            )

        row = MatchGameRating.objects.get(user=self.user, game_id=self.game1.game_id)
        self.assertEqual(row.star_rating, 1)
        self.assertEqual(row.rating_count, 1)

        pref = UserPreference.objects.get(user=self.user)
        self.assertEqual(len(pref.match_vector), 14)


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

    def test_post_responses_missing_retry_no_returns_400(self):
        response = self.client.post(
            self.url,
            {
                "genre_id": 2,
                "match_result": [{"game_id": self.game1.game_id, "rating": 4}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("retry_no", response.data["error_detail"])
