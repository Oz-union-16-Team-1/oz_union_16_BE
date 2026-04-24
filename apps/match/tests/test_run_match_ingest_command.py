from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase


class RunMatchIngestCommandTest(SimpleTestCase):
    """커맨드 주요 출력 라인을 검증한다."""

    @patch(
        "apps.match.management.commands.run_match_ingest.MatchCandidateFilterBatchService.run"
    )
    def test_command_output(self, mock_run):
        mock_run.return_value = (
            [{"id": 1}],
            {
                "total_fetched": 10,
                "total_passed": 1,
                "total_excluded": 9,
                "excluded_reasons": {"invalid_status": 9},
            },
        )

        out = StringIO()
        call_command("run_match_ingest", stdout=out)
        output = out.getvalue()

        self.assertIn("[MATCH][INGEST] 배치 실행 완료", output)
        self.assertIn("total_fetched: 10", output)
        self.assertIn("excluded_reasons:", output)
