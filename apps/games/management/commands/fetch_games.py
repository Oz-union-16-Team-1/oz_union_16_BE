from django.core.management.base import BaseCommand

from apps.games.service.game_sync_services import GameSyncService


class Command(BaseCommand):
    help = "IGDB API로부터 게임 데이터를 수집하여 DB에 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--page-size", type=int, default=500)
        parser.add_argument("--max-pages", type=int, default=0)
        parser.add_argument("--pc-only", action="store_true")
        parser.add_argument("--translate-ko", action="store_true")

    def handle(self, *args, **options):
        page_size = options["page_size"]
        max_pages = options["max_pages"]
        pc_only = options["pc_only"]
        translate_ko = options["translate_ko"]

        self.stdout.write("데이터 수집 중...")
        stats = GameSyncService.sync_all_games(
            page_size=page_size,
            max_pages=max_pages,
            pc_only=pc_only,
            translate_ko=translate_ko,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"동기화 완료! scanned={stats['scanned']} upserted={stats['upserted']}"
            )
        )
