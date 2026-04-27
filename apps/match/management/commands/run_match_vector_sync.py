from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.match.services.vector_sync import MatchVectorSyncService


class Command(BaseCommand):
    help = "매칭 게임 벡터/장르맵 동기화 배치를 실행합니다."

    def handle(self, *args, **options):
        stats = MatchVectorSyncService().run()

        self.stdout.write(self.style.SUCCESS("[MATCH][VECTOR_SYNC] 배치 실행 완료"))
        self.stdout.write(f"- scanned: {stats.scanned}")
        self.stdout.write(f"- upserted_preferences: {stats.upserted_preferences}")
        self.stdout.write(f"- upserted_genre_links: {stats.upserted_genre_links}")
