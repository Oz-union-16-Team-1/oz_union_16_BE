from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import Game
from apps.games.service.game_list_top100_services import GameTop100Service


class GameTop100APITest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.game_main = Game.objects.create(
            game_id=1,
            name="Main Game",
            total_rating=95.56,
            total_rating_count=100,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[12, 999],
            cover="test_image_id",
        )

        bulk_games = []
        for i in range(2, 105):
            bulk_games.append(
                Game(
                    game_id=i,
                    name=f"Game {i}",
                    total_rating=80.0,
                    total_rating_count=60,
                    first_release_date=timezone.now() - timezone.timedelta(days=2),
                    genres=[12],
                )
            )
        Game.objects.bulk_create(bulk_games)

        cls.url = reverse("game_list_top100")

    # ------------------------------------------------------------------ #
    # View 통합 테스트
    # ------------------------------------------------------------------ #

    def test_get_top100_success_and_logic_coverage(self):
        """정상 조회 및 시리얼라이저 분기(반올림, 이미지 URL, 장르 매핑) 검증"""
        response = self.client.get(
            "/api/v1/games/list/top100", {"genre_id": 0, "page_size": 100}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIn("ranked_at", response.data)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("results", response.data)

        self.assertEqual(response.data["count"], 100)
        self.assertEqual(len(response.data["results"]), 100)

        self.assertEqual(
            response.data["results"][0]["thumbnail_url"],
            "https://images.igdb.com/igdb/image/upload/t_720p/test_image_id.jpg",
        )

        self.assertEqual(float(response.data["results"][0]["rating"]), 95.6)

    def test_view_missing_and_invalid_param(self):
        """파라미터 누락 및 잘못된 값 검증"""
        self.assertEqual(self.client.get(self.url).status_code, 400)
        self.assertEqual(
            self.client.get(self.url, {"genre_id": "abc"}).status_code, 400
        )
        self.assertEqual(self.client.get(self.url, {"genre_id": 99}).status_code, 400)

    def test_view_503_error_coverage(self):
        """View의 Exception 블록(503 에러) 커버"""
        with patch(
            "apps.games.service.game_list_top100_services.GameTop100Service.get_top_100_games"
        ) as mocked:
            mocked.side_effect = Exception("Internal Error")
            response = self.client.get(self.url, {"genre_id": 0})
            self.assertEqual(response.status_code, 503)

    def test_service_empty_mapping_coverage(self):
        """매핑 테이블에 없는 genre_id → 빈 리스트 반환 (line 70)"""
        result = GameTop100Service.get_top_100_games(genre_id=99)
        self.assertEqual(result, [])

    def test_service_search_icontains_coverage(self):
        """일반 검색 (line 64): fuzzy=False + search 키워드"""
        result = GameTop100Service.get_top_100_games(
            genre_id=0, search="Main", fuzzy=False
        )
        self.assertGreater(len(result), 0)
        self.assertTrue(all("main" in g.name.lower() for g in result))

    def test_service_search_fuzzy_coverage(self):
        """퍼지 검색 (lines 58~62): fuzzy=True + 단어 단위 OR"""
        result = GameTop100Service.get_top_100_games(
            genre_id=0, search="Main Game", fuzzy=True
        )
        self.assertGreater(len(result), 0)

    def test_service_genre_filter_coverage(self):
        """장르 Q 필터 빌드 (lines 72~75): 유효한 genre_id"""
        # genre_id=3(RPG) → GENRE_MAPPING[3] = [12]
        # setUpTestData의 게임들이 genres=[12] 포함
        result = GameTop100Service.get_top_100_games(genre_id=3)
        self.assertGreater(len(result), 0)

    def test_service_excludes_games_released_before_1980(self):
        """1980년 이전 출시 게임은 목록 후보에서 제외한다."""
        Game.objects.create(
            game_id=1900,
            name="Old Arcade Game",
            total_rating=100.0,
            total_rating_count=999,
            first_release_date=datetime(1979, 12, 31, tzinfo=dt_timezone.utc),
            genres=[12],
        )

        result = GameTop100Service.get_top_100_games(genre_id=0)

        self.assertNotIn(1900, {game.game_id for game in result})

    def test_service_uses_rating_fallback_for_sparse_genre(self):
        """엄격한 TOP100 조건을 못 채우는 장르는 완화된 평점 기준으로 보충한다."""
        Game.objects.create(
            game_id=2200,
            name="Sparse Genre Rated Game",
            total_rating=91.0,
            total_rating_count=10,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(genre_id=13)

        self.assertEqual([game.game_id for game in result], [2200])

    def test_service_uses_popularity_fallback_when_ratings_are_missing(self):
        """평점 데이터가 부족한 장르는 follows/hypes/출시일 기준으로 보충한다."""
        Game.objects.create(
            game_id=2300,
            name="Popular No Rating Game",
            total_rating=None,
            total_rating_count=None,
            rating=None,
            rating_count=None,
            aggregated_rating=None,
            aggregated_rating_count=None,
            follows=1000,
            hypes=10,
            first_release_date=timezone.now() - timezone.timedelta(days=2),
            genres=[7],
        )
        Game.objects.create(
            game_id=2301,
            name="Less Popular No Rating Game",
            total_rating=None,
            total_rating_count=None,
            rating=None,
            rating_count=None,
            aggregated_rating=None,
            aggregated_rating_count=None,
            follows=100,
            hypes=50,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(genre_id=13)

        self.assertEqual([game.game_id for game in result[:2]], [2300, 2301])

    def test_service_collection_dedup_coverage(self):
        """collection 기반 중복 제거 (lines 88~90): 동일 collection skip"""
        Game.objects.create(
            game_id=200,
            name="Series Alpha",
            total_rating=90.0,
            total_rating_count=60,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[12],
            collection=777,
        )
        Game.objects.create(
            game_id=201,
            name="Series Alpha: Sequel",
            total_rating=89.0,
            total_rating_count=60,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[12],
            collection=777,  # 동일 collection → skip 대상
        )
        result = GameTop100Service.get_top_100_games(genre_id=0)

        collection_777 = [g for g in result if g.collection == 777]
        self.assertEqual(len(collection_777), 1)
        self.assertEqual(collection_777[0].name, "Series Alpha")

    def test_service_basename_dedup_coverage(self):
        """base_name 기반 중복 제거 (line 96): 동일 base_name skip"""
        Game.objects.create(
            game_id=210,
            name="Omega Game: Director's Cut",
            total_rating=88.0,
            total_rating_count=60,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[12],
        )
        Game.objects.create(
            game_id=211,
            name="Omega Game: Enhanced Edition",
            total_rating=87.0,
            total_rating_count=60,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[12],
        )
        result = GameTop100Service.get_top_100_games(genre_id=0)

        omega_games = [g for g in result if g.name.startswith("Omega Game")]
        self.assertEqual(len(omega_games), 1)
        self.assertEqual(omega_games[0].name, "Omega Game: Director's Cut")
