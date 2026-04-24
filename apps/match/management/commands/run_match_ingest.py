from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.match.services.candidate_filter_batch import MatchCandidateFilterBatchService


class Command(BaseCommand):
    help = "game_list 기반 매칭 후보 필터 배치를 실행하고 통계를 출력합니다."

    def handle(self, *args, **options):
        service = MatchCandidateFilterBatchService()
        passed, stats = service.run()

        self.stdout.write(self.style.SUCCESS("[MATCH][INGEST] 배치 실행 완료"))
        self.stdout.write("=== ingest stats ===")
        self.stdout.write(f"total_fetched: {stats.get('total_fetched', 0)}")
        self.stdout.write(f"total_passed: {stats.get('total_passed', 0)}")
        self.stdout.write(f"total_excluded: {stats.get('total_excluded', 0)}")
        self.stdout.write(f"passed_preview_count: {len(passed)}")
        self.stdout.write("excluded_reasons:")

        excluded_reasons = stats.get("excluded_reasons", {})
        if not excluded_reasons:
            self.stdout.write("  - none")
        else:
            for reason, count in sorted(excluded_reasons.items()):
                self.stdout.write(f"  - {reason}: {count}")
