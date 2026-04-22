from unittest.mock import patch

from django.test import SimpleTestCase

from apps.match.services.batch_ingest import MatchBatchIngestService


class BatchIngestTest(SimpleTestCase):
    # 마지막 페이지(len < page_size)에서 종료되는지 확인.
    @patch("apps.match.services.batch_ingest.filter_games_with_reasons")
    @patch("apps.match.services.batch_ingest.igdb_client.query_games")
    def test_run_stops_on_last_page(self, mock_query_games, mock_filter):
        mock_query_games.side_effect = [
            [{"id": 1}, {"id": 2}, {"id": 3}],
            [{"id": 4}],
        ]
        mock_filter.return_value = ([{"id": 1}], {"invalid_status": 1})

        service = MatchBatchIngestService(page_size=3, max_pages=10, request_interval=0)
        _, stats = service.run()

        self.assertEqual(mock_query_games.call_count, 2)
        self.assertEqual(stats["total_fetched"], 4)
        self.assertEqual(stats["total_passed"], 1)
