from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.match.models import MatchGameGenreMap, MatchGamePreference
from apps.match.services.candidates_query import (
    MatchCandidatesDataUnavailable,
    MatchCandidatesQueryService,
)
from apps.match.services.candidates_selector import MatchCandidatesSelectorService
from apps.match.services.game_list_query import _to_unix_timestamp, to_ingest_row
from apps.match.services.ingest_filters import filter_games_with_reasons, validate_game
from apps.users.models import UserLikeBookmark


class MatchCandidatesFixtureMixin:
    @staticmethod
    def _vector(seed: int) -> list[float]:
        return [(((seed + idx * 7) % 23) - 11) / 11.0 for idx in range(14)]

    @classmethod
    def _create_game(
        cls,
        *,
        game_id: int,
        genre_ids: list[int],
        summary: str = "Default summary",
        storyline: str = "",
        video_id: str = "trailer_id",
        rating: float | None = 82.3,
        rating_count: int = 35,
        aggregated_rating: float | None = None,
        aggregated_rating_count: int = 0,
        total_rating: float | None = 82.3,
        total_rating_count: int = 35,
        game_type: int | None = 0,
        category: int | None = None,
        status_value: int | None = 0,
        first_release_date: datetime | None = None,
        is_ban: bool = False,
    ) -> Game:
        game = Game.objects.create(
            game_id=game_id,
            name=f"Game {game_id}",
            slug=f"game-{game_id}",
            summary=summary,
            storyline=storyline,
            category=category,
            status=status_value,
            first_release_date=first_release_date
            or datetime(2021, 5, 1, tzinfo=timezone.utc),
            rating=rating,
            rating_count=rating_count,
            aggregated_rating=aggregated_rating,
            aggregated_rating_count=aggregated_rating_count,
            total_rating=total_rating,
            total_rating_count=total_rating_count,
            game_modes=[1, 2],
            player_perspectives=[2],
            themes=[1],
            genres=genre_ids,
            videos=[{"video_id": video_id}],
            game_type=game_type,
            is_ban=is_ban,
        )

        MatchGamePreference.objects.create(
            game_id=game,
            game_preference_vector=cls._vector(game_id),
        )
        for genre_id in genre_ids:
            MatchGameGenreMap.objects.create(game_id=game, igdb_genre_id=genre_id)
        return game


class MatchCandidatesAPITest(MatchCandidatesFixtureMixin, TestCase):
    valid_genre2_ids: list[int]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("match-candidates")
        cls.user = get_user_model().objects.create_user(
            login_id="candidates_api_user",
            password="Pass1234!",
            name="테스터",
            nickname="candidates_tester",
            gender="M",
        )

        # genre_id=2(어드벤처/플랫폼) -> igdb [2, 10]
        cls.valid_genre2_ids = []
        for gid in range(2001, 2021):
            game = cls._create_game(game_id=gid, genre_ids=[2])
            cls.valid_genre2_ids.append(game.game_id)

        # ingest 필터 탈락(평점/카운트 모든 경로 실패)
        cls._create_game(
            game_id=2100,
            genre_ids=[2],
            rating=49.0,
            rating_count=1,
            total_rating=49.0,
            total_rating_count=1,
            aggregated_rating=59.0,
            aggregated_rating_count=2,
        )

        # is_ban=True 탈락
        cls._create_game(game_id=2101, genre_ids=[2], is_ban=True)

        # genre_id=8(음악/리듬) -> igdb [13], description/rating/trailer 정규화 검증용
        long_summary = "A" * 120 + " " + "B" * 120 + " " + "C" * 120
        cls.genre8_game = cls._create_game(
            game_id=2800,
            genre_ids=[13],
            summary=long_summary,
            rating=None,
            video_id="xyz123",
        )

        # liked 제외 검증용
        cls.liked_excluded_game_id = cls.valid_genre2_ids[0]
        UserLikeBookmark.objects.create(
            user=cls.user,
            game_id=cls.liked_excluded_game_id,
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_candidates_success_runs_real_pipeline(self):
        response = self.client.get(self.url, {"genre_id": 2, "retry_no": 0})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["genre_id"], 2)
        self.assertEqual(response.data["count"], 5)

        results = response.data["results"]
        game_ids = [row["game_id"] for row in results]

        self.assertEqual(len(game_ids), len(set(game_ids)))
        self.assertNotIn(self.liked_excluded_game_id, game_ids)
        self.assertNotIn(2100, game_ids)
        self.assertNotIn(2101, game_ids)

        for row in results:
            self.assertIn("title", row)
            self.assertIn("trailer_url", row)
            self.assertIn("description", row)
            self.assertIn("genres", row)
            self.assertIn("rating", row)
            self.assertIsInstance(row["genres"], list)

    def test_get_candidates_retry_no_zero_is_deterministic(self):
        first = self.client.get(self.url, {"genre_id": 2, "retry_no": 0})
        second = self.client.get(self.url, {"genre_id": 2, "retry_no": 0})

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)

        first_ids = [x["game_id"] for x in first.data["results"]]
        second_ids = [x["game_id"] for x in second.data["results"]]
        self.assertEqual(first_ids, second_ids)

    def test_get_candidates_genre8_normalization(self):
        response = self.client.get(self.url, {"genre_id": 8, "retry_no": 0})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

        item = response.data["results"][0]
        self.assertEqual(item["game_id"], self.genre8_game.game_id)
        self.assertEqual(item["rating"], 0.0)
        self.assertEqual(item["trailer_url"], "https://www.youtube.com/watch?v=xyz123")
        self.assertLessEqual(len(item["description"]), 201)
        self.assertTrue(item["description"].endswith("…"))

    def test_get_candidates_not_found_when_no_candidates(self):
        response = self.client.get(self.url, {"genre_id": 7, "retry_no": 0})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_detail"],
            "해당 장르의 게임을 찾을 수 없습니다.",
        )

    def test_get_candidates_unauthorized_returns_401(self):
        anonymous_client = APIClient()
        response = anonymous_client.get(self.url, {"genre_id": 2})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error_detail", response.data)

    def test_get_candidates_invalid_genre_id_returns_400(self):
        for invalid in [0, 9, "abc"]:
            with self.subTest(genre_id=invalid):
                response = self.client.get(self.url, {"genre_id": invalid})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("genre_id", response.data["error_detail"])

    def test_get_candidates_invalid_retry_no_returns_400(self):
        for invalid in [-1, "abc"]:
            with self.subTest(retry_no=invalid):
                response = self.client.get(
                    self.url,
                    {"genre_id": 2, "retry_no": invalid},
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("retry_no", response.data["error_detail"])

    @patch("apps.match.views.candidates.MatchCandidatesQueryService.get_candidates")
    def test_get_candidates_service_unavailable_returns_503(self, mock_get_candidates):
        mock_get_candidates.side_effect = MatchCandidatesDataUnavailable()

        response = self.client.get(self.url, {"genre_id": 2, "retry_no": 0})

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data["error_detail"],
            "외부 게임 데이터 서비스가 일시적으로 불가합니다.",
        )


class MatchCandidatesServiceHelperTest(MatchCandidatesFixtureMixin, TestCase):
    def test_query_service_helper_methods(self):
        svc = MatchCandidatesQueryService()

        self.assertEqual(svc._normalize_rating(None), 0.0)
        self.assertEqual(svc._normalize_rating(True), 0.0)
        self.assertEqual(svc._normalize_rating("82.37"), 82.4)

        long_text = "word " * 80
        self.assertTrue(svc._normalize_description(long_text, "").endswith("…"))
        self.assertEqual(svc._normalize_description("", "story"), "story")

        self.assertEqual(svc._to_trailer_url([]), "")
        self.assertEqual(
            svc._to_trailer_url([{"video_id": "abc"}]),
            "https://www.youtube.com/watch?v=abc",
        )
        self.assertEqual(
            svc._to_trailer_url([{"id": "https://youtu.be/x"}]),
            "https://youtu.be/x",
        )

    def test_selector_service_helper_methods(self):
        svc = MatchCandidatesSelectorService()

        self.assertEqual(svc._normalize_vector(None), [])
        self.assertEqual(svc._normalize_vector("abc"), [])
        self.assertEqual(svc._normalize_vector(123), [])
        self.assertEqual(svc._normalize_vector([1, "2", 3.5]), [1.0, 2.0, 3.5])

        self.assertEqual(svc._weighted_cosine_distance([], [1.0]), 1.0)
        self.assertEqual(svc._weighted_cosine_distance([0.0, 0.0], [1.0, 1.0]), 1.0)
        self.assertAlmostEqual(
            svc._weighted_cosine_distance([1.0, 0.0], [1.0, 0.0]),
            0.0,
            places=6,
        )

        # candidates 전용 가중치: dim14(인기도)는 약가중
        weights = svc._candidate_weights(14)
        self.assertEqual(len(weights), 14)
        self.assertLess(weights[-1], weights[0])  # dim14 < dim1

        # dim14 차이만 있을 때 거리 영향은 존재하되 과도하지 않아야 함
        a = [1.0] + [0.0] * 12 + [1.0]
        b = [1.0] + [0.0] * 12 + [0.0]
        dist = svc._weighted_cosine_distance(a, b)
        self.assertGreater(dist, 0.0)
        self.assertLess(dist, 0.2)

        self.assertEqual(svc._safe_retry_no(-1), 0)
        self.assertEqual(svc._safe_retry_no("x"), 0)

        seed1 = svc._seed(
            user_id=1, api_genre_id=2, retry_no=0, today=datetime.now().date()
        )
        seed2 = svc._seed(
            user_id=1, api_genre_id=2, retry_no=0, today=datetime.now().date()
        )
        self.assertEqual(seed1, seed2)

    def test_selector_apply_ingest_filters_uses_game_list_row_converter(self):
        pass_game = self._create_game(game_id=9001, genre_ids=[2])
        fail_game = self._create_game(
            game_id=9002,
            genre_ids=[2],
            rating=10.0,
            rating_count=1,
            total_rating=10.0,
            total_rating_count=1,
            aggregated_rating=10.0,
            aggregated_rating_count=1,
        )

        svc = MatchCandidatesSelectorService()
        filtered = svc._apply_ingest_filters([pass_game.game_id, fail_game.game_id])

        self.assertEqual(filtered, [9001])


class MatchIngestFilterAndGameListQueryTest(TestCase):
    def _base_game_row(self) -> dict[str, object]:
        return {
            "id": 1,
            "game_type": 0,
            "category": None,
            "status": 0,
            "rating": 80.0,
            "rating_count": 25,
            "total_rating": 80.0,
            "total_rating_count": 25,
            "aggregated_rating": None,
            "aggregated_rating_count": 0,
            "first_release_date": 1704067200,
            "genres": [2],
            "themes": [1],
            "game_modes": [1],
            "player_perspectives": [2],
            "videos": [{"video_id": "x"}],
            "summary": "ok",
            "storyline": "",
        }

    def test_validate_game_reason_matrix(self):
        base = self._base_game_row()
        self.assertIsNone(validate_game(base.copy()))

        row = base.copy()
        row["game_type"] = 3
        self.assertEqual(validate_game(row), "invalid_category")

        row = base.copy()
        row["status"] = 2
        self.assertEqual(validate_game(row), "invalid_status")

        row = base.copy()
        row["rating_count"] = 1
        row["total_rating_count"] = 1
        row["aggregated_rating_count"] = 0
        self.assertEqual(validate_game(row), "low_rating_or_count")

        row = base.copy()
        row["aggregated_rating"] = 20.0
        row["aggregated_rating_count"] = 3
        self.assertEqual(validate_game(row), "low_aggregated_rating")

        row = base.copy()
        row["summary"] = ""
        row["storyline"] = ""
        self.assertEqual(validate_game(row), "incomplete_data")

        row = base.copy()
        row["first_release_date"] = 915148800
        self.assertEqual(validate_game(row), "too_old_release_or_missing")

    def test_validate_game_allows_total_rating_path_and_missing_category(self):
        row = self._base_game_row()
        row["game_type"] = None
        row["category"] = None
        row["rating"] = None
        row["rating_count"] = 0
        row["total_rating"] = 70.0
        row["total_rating_count"] = 25

        self.assertIsNone(validate_game(row))

    def test_filter_games_with_reasons_counts(self):
        good = self._base_game_row()
        bad = self._base_game_row()
        bad["status"] = 2

        passed, reasons = filter_games_with_reasons([good, bad])

        self.assertEqual(len(passed), 1)
        self.assertEqual(reasons.get("invalid_status"), 1)

    def test_game_list_query_row_conversion(self):
        self.assertIsNone(_to_unix_timestamp(None))

        naive_dt = datetime(2024, 1, 1, 0, 0, 0)
        aware_dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(_to_unix_timestamp(naive_dt), 1704067200)
        self.assertEqual(_to_unix_timestamp(aware_dt), 1704067200)

        row = to_ingest_row(
            {
                "game_id": 123,
                "first_release_date": aware_dt,
                "name": "x",
            }
        )
        self.assertEqual(row["id"], 123)
        self.assertEqual(row["first_release_date"], 1704067200)
