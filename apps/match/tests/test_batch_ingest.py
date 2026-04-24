from unittest.mock import patch

from django.test import SimpleTestCase

from apps.match.services.candidate_filter_batch import MatchCandidateFilterBatchService


class CandidateFilterBatchTest(SimpleTestCase):
    # DB 조회 결과를 필터링하고 통계를 집계하는지 확인.
    @patch("apps.match.services.candidate_filter_batch.filter_games_with_reasons")
    @patch("apps.match.services.candidate_filter_batch.fetch_ingest_rows_from_game_list")
    def test_run_collects_and_counts(self, mock_fetch_rows, mock_filter):
        mock_fetch_rows.return_value = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]
        mock_filter.return_value = ([{"id": 1}], {"invalid_status": 1})

        service = MatchCandidateFilterBatchService(page_size=3, max_pages=10)
        _, stats = service.run()

        mock_fetch_rows.assert_called_once_with(page_size=3, max_pages=10)
        self.assertEqual(stats["total_fetched"], 4)
        self.assertEqual(stats["total_passed"], 1)
        self.assertEqual(stats["total_excluded"], 3)
