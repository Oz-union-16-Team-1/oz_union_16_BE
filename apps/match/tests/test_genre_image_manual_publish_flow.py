from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.games.models import Game
from apps.match.models import MatchGenreImagePublished
from apps.match.services.genre_image_candidates import GenreImageCandidatesService
from apps.match.services.genre_image_publish import MatchGenreImagePublishService


class MatchGenreImageCandidatesBackfillTest(SimpleTestCase):
    def setUp(self) -> None:
        self.service = GenreImageCandidatesService()

    @staticmethod
    def _candidate(game_id: int, release_ts: int) -> dict:
        return {
            "game_id": game_id,
            "name": f"game-{game_id}",
            "rating": 88.8,
            "rating_count": 120,
            "release_ts": release_ts,
            "images": [
                {
                    "url": f"https://images.igdb.com/igdb/image/upload/t_1080p/{game_id}.jpg",
                    "source": "cover",
                    "label": "대표 커버",
                }
            ],
        }

    def test_backfill_short_genres_fills_to_limit(self):
        now_ts = 1_700_000_000

        ranked_by_genre = {
            gid: [self._candidate(gid * 1000 + i, now_ts - i) for i in range(1, 8)]
            for gid in range(1, 9)
        }

        selected_by_genre = {
            gid: [self._candidate(gid * 1000 + i, now_ts - i) for i in range(1, 6)]
            for gid in range(1, 9)
        }

        # 부족 장르 시나리오
        selected_by_genre[8] = [self._candidate(8001, now_ts)]
        selected_by_genre[5] = [
            self._candidate(5001, now_ts),
            self._candidate(5002, now_ts - 1),
            self._candidate(5003, now_ts - 2),
        ]

        out = self.service._backfill_short_genres(
            selected_by_genre=selected_by_genre,
            ranked_by_genre=ranked_by_genre,
            limit_per_genre=5,
        )

        for gid in range(1, 9):
            self.assertEqual(len(out[gid]), 5)


class MatchGenreImageManualPublishFlowTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = get_user_model().objects.create_user(
            login_id="genre_manual_publish_user",
            password="Pass1234!",
            name="테스터",
            nickname="genre_manual",
            gender="M",
        )

        # seed_or_refresh 테스트용 게임 8개
        for gid in range(1, 9):
            Game.objects.create(
                game_id=1000 + gid,
                name=f"seed-game-{gid}",
                slug=f"seed-game-{gid}",
            )

        # API 조회 테스트용 게임
        cls.api_game = Game.objects.create(
            game_id=99999,
            name="api-game",
            slug="api-game",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("match-genres-image-url")

    @staticmethod
    def _candidate(game_id: int, genre_id: int) -> dict:
        return {
            "game_id": game_id,
            "name": f"seed-game-{genre_id}",
            "rating": 91.1,
            "rating_count": 150,
            "release_ts": 1_700_000_000,
            "images": [
                {
                    "url": f"https://images.igdb.com/igdb/image/upload/t_1080p/co{game_id}.jpg",
                    "source": "cover",
                    "label": "대표 커버",
                }
            ],
        }

    def test_seed_or_refresh_then_api_returns_published_image(self):
        service = MatchGenreImagePublishService()

        candidates_by_genre = {
            gid: [self._candidate(1000 + gid, gid)] for gid in range(1, 9)
        }

        with patch.object(
            service, "build_candidates", return_value=candidates_by_genre
        ):
            updated, missing = service.seed_or_refresh(
                user=self.user, limit_per_genre=5
            )

        self.assertEqual(updated, 8)
        self.assertEqual(missing, 0)
        self.assertEqual(MatchGenreImagePublished.objects.count(), 8)

        response = self.client.get(self.url, {"genre_id": 5})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["genre_id"], 5)
        self.assertIn("image_url", response.data)
        self.assertTrue(response.data["image_url"].startswith("https://"))

    def test_get_genre_image_returns_404_when_unpublished(self):
        # 아무 게시본도 만들지 않으면 404
        response = self.client.get(self.url, {"genre_id": 2})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error_detail", response.data)

    def test_get_genre_image_returns_published_row(self):
        MatchGenreImagePublished.objects.create(
            api_genre_id=8,
            game=self.api_game,
            image_url="https://images.igdb.com/igdb/image/upload/t_1080p/manual.jpg",
            selected_by=self.user,
        )

        response = self.client.get(self.url, {"genre_id": 8})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["genre_id"], 8)
        self.assertEqual(
            response.data["image_url"],
            "https://images.igdb.com/igdb/image/upload/t_1080p/manual.jpg",
        )
