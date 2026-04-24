from django.core.management.base import BaseCommand

from apps.games.service.game_sync_services import GameSyncService


class Command(BaseCommand):
    help = "IGDB API로부터 게임 데이터를 수집하여 DB에 저장합니다."

    def handle(self, *args, **options):
        self.stdout.write("데이터 수집 중...")
        GameSyncService.sync_top_games()
        self.stdout.write(self.style.SUCCESS("동기화 완료!"))
