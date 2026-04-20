from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.match.services.batch_ingest import MatchBatchIngestService


class Command(BaseCommand):
    help = "매칭 IGDB 수집 배치를 실행하고 필터 통계를 출력합니다."

    def handle(self, *args, **options):
        # 운영 전 수동 점검 시, 필터 품질을 reason 분포로 빠르게 확인하기 위한 커맨드.
        service = MatchBatchIngestService()
        passed, stats = service.run()

        self.stdout.write(self.style.SUCCESS("[MATCH][INGEST] 배치 실행 완료"))
        self.stdout.write(f"- total_fetched: {stats['total_fetched']}")
        self.stdout.write(f"- total_passed: {stats['total_passed']}")
        self.stdout.write(f"- total_excluded: {stats['total_excluded']}")
        self.stdout.write("- excluded_reasons:")
        for reason, count in sorted(stats["excluded_reasons"].items()):
            self.stdout.write(f"  - {reason}: {count}")

        self.stdout.write(
            f"- passed_preview_count: {len(passed)}"
        )  # 다음 pr에서 DB/Redis 저장 추가
