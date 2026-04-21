from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.match.services.genre_image_batch import MatchGenreImageBatchService


class Command(BaseCommand):
    help = "장르 대표 이미지 일간 배치를 실행합니다."

    def handle(self, *args, **options):
        result = MatchGenreImageBatchService().run()

        self.stdout.write(self.style.SUCCESS("[MATCH][GENRE_IMAGE] 배치 실행 완료"))
        self.stdout.write(f"- cache_key: {result['cache_key']}")
        self.stdout.write(f"- updated_count: {result['updated_count']}")
