from django.test import TestCase
from django.utils import timezone

from apps.games.models import Game
from apps.match.constants import MATCH_INGEST_REQUIRED_PLATFORM
from apps.match.services.game_list_query import fetch_ingest_rows_from_game_list


class GameListQueryTest(TestCase):
    def test_fetch_maps_fields_and_converts_release_ts(self):
        """game_id/id 변환, first_release_date timestamp 변환, platforms 주입을 검증한다."""
        release_dt = timezone.now()

        Game.objects.create(
            game_id=10,
            name="Game A",
            slug="game-a",
            first_release_date=release_dt,
            is_ban=False,
        )

        rows = fetch_ingest_rows_from_game_list(page_size=10, max_pages=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], 10)
        self.assertEqual(rows[0]["first_release_date"], int(release_dt.timestamp()))
        self.assertEqual(rows[0]["platforms"], [MATCH_INGEST_REQUIRED_PLATFORM])

    def test_fetch_excludes_banned_games(self):
        """is_ban=True 게임은 조회 결과에서 제외되어야 한다."""
        Game.objects.create(game_id=1, name="Allowed", slug="allowed", is_ban=False)
        Game.objects.create(game_id=2, name="Banned", slug="banned", is_ban=True)

        rows = fetch_ingest_rows_from_game_list(page_size=10, max_pages=1)
        ids = [row["id"] for row in rows]

        self.assertEqual(ids, [1])

    def test_fetch_orders_by_game_id_and_respects_paging_limit(self):
        """game_id 오름차순 + page_size/max_pages 제한이 적용되는지 검증한다."""
        Game.objects.create(game_id=30, name="G30", slug="g30", is_ban=False)
        Game.objects.create(game_id=10, name="G10", slug="g10", is_ban=False)
        Game.objects.create(game_id=20, name="G20", slug="g20", is_ban=False)

        rows = fetch_ingest_rows_from_game_list(page_size=1, max_pages=2)
        ids = [row["id"] for row in rows]

        self.assertEqual(ids, [10, 20])
