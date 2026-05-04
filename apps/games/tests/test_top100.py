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
            name_ko="메인 게임",
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
        self.assertEqual(response.data["results"][0]["name"], "메인 게임 (Main Game)")
        self.assertNotIn("title", response.data["results"][0])
        self.assertNotIn("title_ko", response.data["results"][0])
        self.assertNotIn("title_original", response.data["results"][0])

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

    def test_service_search_matches_korean_title(self):
        """한글 검색어도 name_ko 기준으로 검색할 수 있다."""
        self.game_main.name_ko = "메인 게임"
        self.game_main.save(update_fields=["name_ko"])

        result = GameTop100Service.get_top_100_games(
            genre_id=0, search="메인", fuzzy=False
        )

        self.assertEqual([game.game_id for game in result], [self.game_main.game_id])

    def test_service_search_fuzzy_coverage(self):
        """퍼지 검색 (lines 58~62): fuzzy=True + 단어 단위 OR"""
        result = GameTop100Service.get_top_100_games(
            genre_id=0, search="Main Game", fuzzy=True
        )
        self.assertGreater(len(result), 0)

    def test_service_search_fuzzy_matches_korean_title(self):
        """퍼지 검색도 name_ko를 함께 사용한다."""
        self.game_main.name_ko = "메인 게임"
        self.game_main.save(update_fields=["name_ko"])

        result = GameTop100Service.get_top_100_games(
            genre_id=0, search="메인 액션", fuzzy=True
        )

        self.assertEqual([game.game_id for game in result], [self.game_main.game_id])

    def test_service_genre_filter_coverage(self):
        """장르 Q 필터 빌드 (lines 72~75): 유효한 genre_id"""
        # genre_id=3(RPG) → GENRE_MAPPING[3] = [12]
        # setUpTestData의 게임들이 genres=[12] 포함
        result = GameTop100Service.get_top_100_games(genre_id=3)
        self.assertGreater(len(result), 0)

    def test_service_excludes_games_before_min_release_year(self):
        """1980년 이전 출시 게임은 목록 후보에서 제외한다."""
        Game.objects.create(
            game_id=1900,
            name="Old Arcade Game",
            total_rating=100.0,
            total_rating_count=999,
            first_release_date=datetime(
                GameTop100Service.MIN_RELEASE_YEAR - 1,
                12,
                31,
                tzinfo=dt_timezone.utc,
            ),
            genres=[12],
        )

        result = GameTop100Service.get_top_100_games(genre_id=0)

        self.assertNotIn(1900, {game.game_id for game in result})

    def test_service_excludes_offline_cancelled_and_delisted_games(self):
        """서비스 종료/취소/판매중지 상태 게임은 검색 결과에서 제외한다."""
        ended_statuses = GameTop100Service.EXCLUDED_SERVICE_STATUSES
        for index, ended_status in enumerate(ended_statuses):
            Game.objects.create(
                game_id=2100 + index,
                name=f"Closed Search Game {index}",
                total_rating=100.0,
                total_rating_count=999,
                first_release_date=timezone.now() - timezone.timedelta(days=1),
                genres=[12],
                status=ended_status,
            )
        Game.objects.create(
            game_id=2110,
            name="Closed Search Game Active",
            total_rating=70.0,
            total_rating_count=50,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[12],
            status=0,
        )

        result = GameTop100Service.get_top_100_games(
            genre_id=0,
            search="Closed Search Game",
        )
        result_ids = {game.game_id for game in result}

        self.assertEqual(result_ids, {2110})

    def test_service_returns_sparse_genre_by_rating_order(self):
        """후보가 적은 장르도 평점순 조회 대상에 포함한다."""
        Game.objects.create(
            game_id=2200,
            name="Sparse Genre Rated Game",
            total_rating=91.0,
            total_rating_count=50,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(genre_id=13)

        self.assertEqual([game.game_id for game in result], [2200])

    def test_service_excludes_games_below_lowest_review_threshold(self):
        """통합 평가 수가 5개 미만인 게임은 목록 후보에서 제외한다."""
        Game.objects.create(
            game_id=2300,
            name="Low Review Count Game",
            total_rating=95.0,
            total_rating_count=4,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[7],
        )
        Game.objects.create(
            game_id=2301,
            name="Enough Review Count Game",
            total_rating=80.0,
            total_rating_count=5,
            first_release_date=timezone.now() - timezone.timedelta(days=1),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(genre_id=13)

        self.assertEqual([game.game_id for game in result], [2301])

    def test_service_orders_final_genre_results_by_rating(self):
        """개별 장르는 후보를 채운 뒤 최종 응답을 평점순으로 반환한다."""
        current_year = timezone.now().year
        Game.objects.create(
            game_id=2310,
            name="Old High Rating Game",
            total_rating=100.0,
            total_rating_count=999,
            first_release_date=datetime(current_year - 1, 1, 1, tzinfo=dt_timezone.utc),
            genres=[7],
        )
        Game.objects.create(
            game_id=2311,
            name="New Lower Rating Game",
            total_rating=50.0,
            total_rating_count=50,
            first_release_date=datetime(current_year, 1, 1, tzinfo=dt_timezone.utc),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(genre_id=13)

        self.assertEqual([game.game_id for game in result[:2]], [2310, 2311])

    def test_service_genre_keeps_bucket_selection_and_sorts_final_results_by_rating(
        self,
    ):
        """최신 연도/리뷰 수 기준으로 후보를 채우되 최종 응답은 평점순으로 반환한다."""
        current_year = timezone.now().year
        Game.objects.create(
            game_id=2320,
            name="Current Year Review 30 Game",
            total_rating=70.0,
            total_rating_count=30,
            first_release_date=datetime(current_year, 1, 1, tzinfo=dt_timezone.utc),
            genres=[7],
        )
        Game.objects.create(
            game_id=2321,
            name="Previous Year Review 50 Game",
            total_rating=100.0,
            total_rating_count=50,
            first_release_date=datetime(current_year - 1, 1, 1, tzinfo=dt_timezone.utc),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(genre_id=13)

        self.assertEqual([game.game_id for game in result[:2]], [2321, 2320])

    def test_service_global_uses_review_50_and_2020_lower_bound(self):
        """전체 장르는 평가 수 50개 이상만 2020년까지 보충한다."""
        current_year = timezone.now().year
        Game.objects.create(
            game_id=2330,
            name="Global Policy Current Low Review",
            total_rating=100.0,
            total_rating_count=30,
            first_release_date=datetime(current_year, 1, 1, tzinfo=dt_timezone.utc),
            genres=[7],
        )
        Game.objects.create(
            game_id=2331,
            name="Global Policy Fallback Review 50",
            total_rating=80.0,
            total_rating_count=50,
            first_release_date=datetime(current_year - 3, 1, 1, tzinfo=dt_timezone.utc),
            genres=[7],
        )
        Game.objects.create(
            game_id=2332,
            name="Global Policy Too Old Review 50",
            total_rating=90.0,
            total_rating_count=50,
            first_release_date=datetime(2019, 1, 1, tzinfo=dt_timezone.utc),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(
            genre_id=0,
            search="Global Policy",
        )

        self.assertEqual([game.game_id for game in result], [2331])

    def test_service_fills_from_lower_review_thresholds_when_needed(self):
        """리뷰 50개 이상 후보가 부족하면 30개, 10개, 5개 이상 후보로 보충한다."""
        primary_release = timezone.now() - timezone.timedelta(days=1)

        games = []
        for i in range(98):
            games.append(
                Game(
                    game_id=2500 + i,
                    name=f"Review 50 Game {i}",
                    total_rating=80.0,
                    total_rating_count=60,
                    first_release_date=primary_release - timezone.timedelta(minutes=i),
                    genres=[7],
                )
            )
        Game.objects.bulk_create(games)
        Game.objects.create(
            game_id=2600,
            name="Review 30 Fallback Game",
            total_rating=90.0,
            total_rating_count=30,
            first_release_date=primary_release - timezone.timedelta(hours=3),
            genres=[7],
        )
        Game.objects.create(
            game_id=2601,
            name="Review 10 Fallback Game",
            total_rating=88.0,
            total_rating_count=10,
            first_release_date=primary_release - timezone.timedelta(hours=4),
            genres=[7],
        )
        Game.objects.create(
            game_id=2602,
            name="Too Low Review Game",
            total_rating=100.0,
            total_rating_count=4,
            first_release_date=primary_release - timezone.timedelta(hours=5),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(genre_id=13)
        result_ids = {game.game_id for game in result}

        self.assertEqual(len(result), 100)
        self.assertIn(2600, result_ids)
        self.assertIn(2601, result_ids)
        self.assertNotIn(2602, result_ids)

    def test_service_includes_older_games_when_top100_is_short(self):
        """조건을 만족하면 과거 출시 게임도 TOP100 후보에 포함한다."""
        recent_release = timezone.now() - timezone.timedelta(days=1)

        games = []
        for i in range(99):
            games.append(
                Game(
                    game_id=2700 + i,
                    name=f"Recent Year Game {i}",
                    total_rating=80.0,
                    total_rating_count=60,
                    first_release_date=recent_release - timezone.timedelta(minutes=i),
                    genres=[7],
                )
            )
        Game.objects.bulk_create(games)
        Game.objects.create(
            game_id=2800,
            name="Older Year Fallback Game",
            total_rating=90.0,
            total_rating_count=60,
            first_release_date=datetime(2019, 6, 1, tzinfo=dt_timezone.utc),
            genres=[7],
        )

        result = GameTop100Service.get_top_100_games(genre_id=13)
        result_ids = {game.game_id for game in result}

        self.assertEqual(len(result), 100)
        self.assertIn(2800, result_ids)

    def test_service_collection_dedup_coverage(self):
        """collection 기반 중복 제거: 동일 collection이면 평점이 높은 게임만 남긴다."""
        latest_release = timezone.now() - timezone.timedelta(days=1)
        older_release = timezone.now() - timezone.timedelta(days=2)
        Game.objects.create(
            game_id=200,
            name="Series Alpha",
            total_rating=90.0,
            total_rating_count=60,
            first_release_date=older_release,
            genres=[12],
            collection=777,
        )
        Game.objects.create(
            game_id=201,
            name="Series Alpha: Sequel",
            total_rating=89.0,
            total_rating_count=60,
            first_release_date=latest_release,
            genres=[12],
            collection=777,  # 동일 collection → skip 대상
        )
        result = GameTop100Service.get_top_100_games(genre_id=0)

        collection_777 = [g for g in result if g.collection == 777]
        self.assertEqual(len(collection_777), 1)
        self.assertEqual(collection_777[0].name, "Series Alpha")

    def test_service_basename_dedup_coverage(self):
        """base_name 기반 중복 제거: 동일 base_name이면 평점이 높은 게임만 남긴다."""
        latest_release = timezone.now() - timezone.timedelta(days=1)
        older_release = timezone.now() - timezone.timedelta(days=2)
        Game.objects.create(
            game_id=210,
            name="Omega Game: Director's Cut",
            total_rating=88.0,
            total_rating_count=60,
            first_release_date=older_release,
            genres=[12],
        )
        Game.objects.create(
            game_id=211,
            name="Omega Game: Enhanced Edition",
            total_rating=87.0,
            total_rating_count=60,
            first_release_date=latest_release,
            genres=[12],
        )
        result = GameTop100Service.get_top_100_games(genre_id=0)

        omega_games = [g for g in result if g.name.startswith("Omega Game")]
        self.assertEqual(len(omega_games), 1)
        self.assertEqual(omega_games[0].name, "Omega Game: Director's Cut")

    def test_service_fills_top100_after_dedup_candidates_are_exhausted(self):
        """중복 제거 후 100개를 못 채우면 남은 순위 후보로 보충한다."""
        games = []
        latest_release = timezone.now() - timezone.timedelta(days=1)
        for i in range(105):
            games.append(
                Game(
                    game_id=2400 + i,
                    name=f"Rhythm Saga: Edition {i}",
                    total_rating=99.0 - (i * 0.1),
                    total_rating_count=60,
                    first_release_date=latest_release - timezone.timedelta(minutes=i),
                    genres=[7],
                )
            )
        Game.objects.bulk_create(games)

        result = GameTop100Service.get_top_100_games(genre_id=13)

        self.assertEqual(len(result), 100)
        self.assertEqual(result[0].game_id, 2400)
