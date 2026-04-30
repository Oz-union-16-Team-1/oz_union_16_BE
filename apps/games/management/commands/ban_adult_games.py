from django.core.management.base import BaseCommand

from apps.games.service.game_sync_services import GameSyncService


class Command(BaseCommand):
    help = "IGDB의 성인용 콘텐츠 조건을 바탕으로 DB 내 PC 게임들을 차단(is_ban=True) 처리합니다."

    def handle(self, *args, **options):
        self.stdout.write("성인 콘텐츠 분석 및 차단 프로세스 시작...")

        # 서비스 레이어의 전체 조회 로직 호출
        total_count = GameSyncService.update_all_banned_pc_games()

        if total_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"성공: 총 {total_count}개의 게임이 차단 목록에 추가되었습니다."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "차단 대상인 게임이 없거나 이미 모두 처리되었습니다."
                )
            )
