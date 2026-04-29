from datetime import datetime, timezone
from unittest.mock import patch

from django.test import TestCase

from apps.games.models import Game
from apps.games.service.game_sync_services import GameSyncService


class GameSyncServiceTest(TestCase):
    def setUp(self):
        # 테스트용 IGDB 원본 데이터 예시
        self.raw_game_data = {
            "id": 12345,
            "name": "Test Adventure Game",
            "slug": "test-adventure-game",
            "summary": "This is a test game summary.",
            "first_release_date": 1714176000,  # 2024-04-27 00:00:00 (UTC)
            "rating": 85.5,
            "total_rating": 87.0,
            "total_rating_count": 100,
            "cover": {"image_id": "co1234"},
            "genres": [12, 31],
            "screenshots": [{"image_id": "sc1234"}],
            "videos": [{"video_id": "yt1234"}],
            "websites": [
                {"category": 1, "url": "https://official.example.com"},
                {"category": 13, "url": "https://store.steampowered.com/app/test"},
            ],
            "involved_companies": [
                {
                    "company": {"name": "Dev Studio"},
                    "developer": True,
                    "publisher": False,
                },
                {
                    "company": {"name": "Pub Studio"},
                    "developer": False,
                    "publisher": True,
                },
            ],
        }

    def test_prepare_game_data_conversion(self):
        """IGDB 원본 데이터가 DB 모델 규격에 맞게 변환되는지 확인"""
        processed_data = GameSyncService.prepare_game_data(self.raw_game_data)

        # 1. 날짜 변환 확인 (타임스탬프 -> datetime)
        expected_date = datetime.fromtimestamp(1714176000, tz=timezone.utc)
        self.assertEqual(processed_data["first_release_date"], expected_date)

        # 2. 기본 필드 값 확인
        self.assertEqual(processed_data["name"], "Test Adventure Game")
        self.assertEqual(processed_data["rating"], 85.5)
        self.assertEqual(processed_data["cover"], "co1234")
        self.assertEqual(processed_data["screenshots"], ["sc1234"])
        self.assertEqual(processed_data["videos"], ["yt1234"])
        self.assertEqual(
            processed_data["websites"],
            [
                {"category": 1, "url": "https://official.example.com"},
                {
                    "category": 13,
                    "url": "https://store.steampowered.com/app/test",
                },
            ],
        )
        self.assertEqual(
            processed_data["involved_companies"],
            [
                {
                    "company_name": "Dev Studio",
                    "developer": True,
                    "publisher": False,
                },
                {
                    "company_name": "Pub Studio",
                    "developer": False,
                    "publisher": True,
                },
            ],
        )

    @patch("apps.games.service.game_sync_services.igdb_client.get_games")
    def test_sync_all_games_success(self, mock_get_games):
        """전체 게임 동기화 로직이 DB에 데이터를 정상적으로 생성/업데이트하는지 확인"""

        # 1. mock_get_games가 한 번은 데이터를 반환하고, 다음엔 빈 리스트를 반환하게 설정 (루프 종료용)
        mock_get_games.side_effect = [[self.raw_game_data], []]

        stats = GameSyncService.sync_all_games(page_size=1, max_pages=1)

        # 2. 결과 통계 확인
        self.assertEqual(stats["scanned"], 1)
        self.assertEqual(stats["upserted"], 1)

        # 3. 실제 DB에 저장되었는지 확인
        game = Game.objects.get(game_id=12345)
        self.assertEqual(game.name, "Test Adventure Game")
        self.assertEqual(game.slug, "test-adventure-game")

    @patch("apps.games.service.game_sync_services.igdb_client.get_games")
    def test_sync_updates_existing_game(self, mock_get_games):
        """이미 존재하는 게임의 정보가 업데이트되는지 확인"""

        # 1. 기존 게임 미리 생성
        Game.objects.create(game_id=12345, name="Old Name", slug="old-slug")

        # 2. 새로운 데이터로 동기화 실행
        mock_get_games.side_effect = [[self.raw_game_data], []]
        GameSyncService.sync_all_games(page_size=1, max_pages=1)

        # 3. DB 값이 업데이트되었는지 확인
        game = Game.objects.get(game_id=12345)
        self.assertEqual(game.name, "Test Adventure Game")  # "Old Name"에서 변경됨
        self.assertEqual(
            Game.objects.count(), 1
        )  # 새로 생성되지 않고 기존 데이터 수정됨

    def test_prepare_game_data_invalid_date(self):
        """유효하지 않은 출시일 데이터가 들어왔을 때 None으로 처리되는지 확인"""
        invalid_data = self.raw_game_data.copy()
        invalid_data["first_release_date"] = "not-a-timestamp"

        processed_data = GameSyncService.prepare_game_data(invalid_data)
        self.assertIsNone(processed_data["first_release_date"])

    def test_prepare_game_data_skips_invalid_metadata_items(self):
        """상세 조회용 메타데이터에 잘못된 값이 들어오면 안전하게 제외한다."""
        raw_data = self.raw_game_data.copy()
        raw_data["websites"] = [
            {"category": 1, "url": "https://official.example.com"},
            {"category": 13},
            "https://store.epicgames.com/test",
            123,
        ]
        raw_data["involved_companies"] = [
            {
                "company": {"name": "Dev Studio"},
                "developer": True,
                "publisher": False,
            },
            {"company": {}, "developer": False, "publisher": True},
            {"developer": True},
            "invalid",
        ]

        processed_data = GameSyncService.prepare_game_data(raw_data)

        self.assertEqual(
            processed_data["websites"],
            [
                {"category": 1, "url": "https://official.example.com"},
                {
                    "category": None,
                    "url": "https://store.epicgames.com/test",
                },
            ],
        )
        self.assertEqual(
            processed_data["involved_companies"],
            [
                {
                    "company_name": "Dev Studio",
                    "developer": True,
                    "publisher": False,
                }
            ],
        )
