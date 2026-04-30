from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.match.models import MatchGameGenreMap, MatchGamePreference, MatchGameRating
from apps.match.services.responses_result_query import (
    MatchResponsesResultDataUnavailable,
    MatchResponsesResultQueryService,
    MatchResponsesResultValidationError,
    RankedGame,
)
from apps.users.models import UserLikeBookmark, UserPreference


class MatchResponsesResultFixtureMixin:
    @classmethod
    def _vector(cls, seed: int) -> list[float]:
        base = (seed % 7) + 1
        return [(base + i) / 100.0 for i in range(14)]

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

        MatchGamePreference.objects.create(
            game_id=game,
            game_preference_vector=cls._vector(game_id),
        )

        for genre_id in genre_ids:
            MatchGameGenreMap.objects.create(game_id=game, igdb_genre_id=genre_id)

        return game


class MatchResponsesResultServiceTest(MatchResponsesResultFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            login_id="resp_result_svc_user",
            password="Pass1234!",
            name="테스터",
            nickname="resp_result_svc_tester",
            gender="M",
        )

        # genre_id=2 -> igdb [2, 10]
        cls.games = []
        for idx, rating in enumerate([96, 91, 88, 84, 79, 75, 70], start=1):
            game = cls._create_game(game_id=9300 + idx, rating=rating, genre_ids=[2])
            cls.games.append(game)

        cls.liked_game_id = cls.games[0].game_id
        UserLikeBookmark.objects.create(user=cls.user, game_id=cls.liked_game_id)

        pref, _ = UserPreference.objects.get_or_create(user=cls.user)
        pref.match_vector = [0.1] * 14
        pref.save(update_fields=["match_vector"])

    def setUp(self) -> None:
        self.service = MatchResponsesResultQueryService()

    def test_get_results_success_with_cursor(self):
        first = self.service.get_results(
            user_id=self.user.id,
            genre_id=2,
            page_size=3,
        )

        self.assertEqual(first["user_id"], self.user.id)
        self.assertGreater(first["count"], 0)
        self.assertLessEqual(first["count"], 15)
        self.assertLessEqual(len(first["results"]), 3)

        if first["next"]:
            first_ids = [row["game_id"] for row in first["results"]]
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

    def test_get_results_wraps_unexpected_exception_as_data_unavailable(self):
        with patch.object(self.service, "_liked_ids", side_effect=RuntimeError("boom")):
            with self.assertRaises(MatchResponsesResultDataUnavailable):
                self.service.get_results(
                    user_id=self.user.id,
                    genre_id=2,
                    page_size=5,
                )

    def test_internal_tau_merge_paginate_and_caps(self):
        items = [
            RankedGame(
                game_id=i,
                title=f"g{i}",
                slug="",
                genres=[],
                thumbnail_url="",
                rating=80.0,
                is_liked=(i % 2 == 0),
                final_score=0.9,
                pop_score=0.8,
                rec_score=0.7,
            )
            for i in range(1, 21)
        ]

        self.assertEqual(self.service._apply_tau_steps([]), [])
        high = self.service._apply_tau_steps(items)
        self.assertEqual(len(high), 15)

        low = [
            RankedGame(
                game_id=999,
                title="low",
                slug="",
                genres=[],
                thumbnail_url="",
                rating=10.0,
                is_liked=False,
                final_score=0.24,
                pop_score=0.2,
                rec_score=0.1,
            )
        ]
        self.assertEqual(self.service._apply_tau_steps(low), [])

        merged = self.service._merge_unique(items[:2], [items[1], items[2]])
        self.assertEqual(len(merged), 3)
        self.assertEqual(self.service._count_liked(merged), 1)
        self.assertEqual(self.service._liked_cap(15), 4)
        self.assertEqual(self.service._take_by_popularity(items, 0), [])

        page, nxt = self.service._paginate(items=high, cursor=None, page_size=3)
        self.assertEqual(len(page), 3)
        self.assertIsNotNone(nxt)

        low_cursor = self.service._encode_cursor(-1.0, 0)
        page2, nxt2 = self.service._paginate(items=high, cursor=low_cursor, page_size=3)
        self.assertEqual(page2, [])
        self.assertIsNone(nxt2)

    def test_internal_vector_numeric_and_thumbnail_helpers(self):
        self.assertEqual(self.service._normalize_page_size(True), 5)
        self.assertEqual(self.service._normalize_page_size(0), 5)
        self.assertEqual(self.service._normalize_page_size(999), 15)

        self.assertEqual(self.service._allowed_game_ids_by_genre(genre_id=99), set())

        self.assertEqual(self.service._to_vector(None), [])
        self.assertEqual(self.service._to_vector("bad"), [])
        self.assertEqual(self.service._to_vector(123), [])
        self.assertEqual(self.service._to_vector([1, "x"]), [])
        self.assertEqual(len(self.service._to_vector([1, 2, 3])), 3)

        self.assertEqual(self.service._cosine_similarity([], []), 0.0)
        self.assertEqual(self.service._cosine_similarity([1.0], [1.0, 2.0]), 0.0)
        self.assertEqual(self.service._cosine_similarity([0.0, 0.0], [1.0, 2.0]), 0.0)

        self.assertEqual(self.service._safe_float(None, default=1.2), 1.2)
        self.assertEqual(self.service._safe_float(object(), default=1.2), 1.2)
        self.assertEqual(self.service._safe_float("3.5", default=0.0), 3.5)

        self.assertEqual(self.service._to_pop_score(None), 0.5)
        self.assertEqual(self.service._to_pop_score(-10), 0.5)
        self.assertEqual(self.service._to_pop_score(250), 1.0)

        self.assertEqual(self.service._to_rec_score("bad"), 0.0)
        self.assertEqual(
            self.service._to_rec_score(datetime(1960, 1, 1, tzinfo=timezone.utc)),
            0.0,
        )
        self.assertGreaterEqual(self.service._to_rec_score(datetime.now()), 0.0)

        self.assertEqual(self.service._normalize_rating(None), 0.0)
        self.assertEqual(self.service._normalize_rating(120), 100.0)

        self.assertEqual(self.service._to_thumbnail_url(""), "")
        self.assertIn(
            "https:",
            self.service._to_thumbnail_url(
                "//images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"
            ),
        )
        self.assertIn(
            "t_1080p",
            self.service._to_thumbnail_url(
                "https://images.igdb.com/igdb/image/upload/t_thumb/abc.jpg"
            ),
        )
        self.assertIn("abc123.jpg", self.service._to_thumbnail_url("abc123"))

        c = self.service._encode_cursor(0.7777777, 123)
        s, g, o = self.service._decode_cursor(c)
        self.assertEqual(g, 123)
        self.assertAlmostEqual(s, 0.777778, places=6)
        self.assertIsNone(o)

    def test_internal_fallback_and_mean_vector_helpers(self):
        self.assertEqual(
            self.service._fallback_popular(
                source_ids=None,
                excluded_ids=set(),
                limit=0,
                liked_ids=set(),
            ),
            [],
        )
        self.assertEqual(
            self.service._fallback_popular(
                source_ids=set(),
                excluded_ids=set(),
                limit=3,
                liked_ids=set(),
            ),
            [],
        )

        self.assertEqual(self.service._genres_by_game(set()), {})
        self.assertIsNone(self.service._mean_vector_for_game_ids([]))
        self.assertIsNone(self.service._mean_vector_for_game_ids([99999999]))

        liked_mean = self.service._load_liked_mean_vector(user_id=self.user.id)
        self.assertIsNotNone(liked_mean)
        self.assertEqual(len(liked_mean), 14)

        self.assertIsNone(self.service._load_disliked_mean_vector(user_id=self.user.id))
        MatchGameRating.objects.create(
            user=self.user,
            game=self.games[1],
            star_rating=1,
            effective_rating="1.00",
            rating_count=1,
        )
        disliked_mean = self.service._load_disliked_mean_vector(user_id=self.user.id)
        self.assertIsNotNone(disliked_mean)
        self.assertEqual(len(disliked_mean), 14)

    def test_internal_series_dedupe_keeps_highest_ranked_variant(self):
        service = MatchResponsesResultQueryService()

        items = [
            RankedGame(
                game_id=1001,
                title="Way of the Hunter",
                slug="way-of-the-hunter",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=80.0,
                is_liked=False,
                final_score=0.95,
                pop_score=0.8,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=1002,
                title="Way of the Hunter Deluxe Edition",
                slug="way-of-the-hunter-deluxe-edition",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=81.0,
                is_liked=False,
                final_score=0.94,
                pop_score=0.8,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=1003,
                title="Way of the Hunter Complete",
                slug="way-of-the-hunter-complete",
                genres=["시뮬레이션"],
                thumbnail_url="",
                rating=82.0,
                is_liked=False,
                final_score=0.93,
                pop_score=0.8,
                rec_score=0.7,
            ),
            RankedGame(
                game_id=2001,
                title="Portal 2",
                slug="portal-2",
                genres=["퍼즐"],
                thumbnail_url="",
                rating=90.0,
                is_liked=False,
                final_score=0.90,
                pop_score=0.9,
                rec_score=0.6,
            ),
        ]

        deduped = service._dedupe_series_variants(items, limit=15)
        deduped_ids = [x.game_id for x in deduped]

        # same series는 상위 1개만 남아야 함
        self.assertIn(1001, deduped_ids)
        self.assertNotIn(1002, deduped_ids)
        self.assertNotIn(1003, deduped_ids)
        self.assertIn(2001, deduped_ids)


class MatchResponsesResultAPITest(MatchResponsesResultFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("match-responses-result")
        cls.user = get_user_model().objects.create_user(
            login_id="resp_result_api_user",
            password="Pass1234!",
            name="테스터",
            nickname="resp_result_api_tester",
            gender="M",
        )

        for idx, rating in enumerate([95, 89, 83, 77, 71], start=1):
            cls._create_game(game_id=9400 + idx, rating=rating, genre_ids=[2])

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_responses_result_success_returns_200(self):
        response = self.client.get(self.url, {"genre_id": 2, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user_id", response.data)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("results", response.data)

    def test_get_responses_result_invalid_genre_returns_400(self):
        response = self.client.get(self.url, {"genre_id": 99, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("genre_id", response.data["error_detail"])

    def test_get_responses_result_invalid_cursor_returns_400(self):
        response = self.client.get(
            self.url,
            {"genre_id": 2, "cursor": "bad-cursor", "page_size": 5},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cursor", str(response.data["error_detail"]))

    def test_get_responses_result_unauthorized_returns_401(self):
        anonymous_client = APIClient()
        response = anonymous_client.get(self.url, {"genre_id": 2})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error_detail", response.data)

    def test_get_responses_result_not_found_returns_404(self):
        response = self.client.get(self.url, {"genre_id": 7, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_detail"], "매칭 추천 결과를 찾을 수 없습니다."
        )

    @patch(
        "apps.match.views.rating_responses_result.MatchResponsesResultQueryService.get_results"
    )
    def test_get_responses_result_service_unavailable_returns_503(
        self, mock_get_results
    ):
        mock_get_results.side_effect = MatchResponsesResultDataUnavailable()

        response = self.client.get(self.url, {"genre_id": 2, "page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data["error_detail"],
            "추천 데이터 조회 중 외부 서비스 오류가 발생했습니다.",
        )
