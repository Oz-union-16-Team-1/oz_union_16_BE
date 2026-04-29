from django.core.management.base import BaseCommand, CommandError

from apps.games.models import Game
from apps.games.service.game_list_top100_services import GameTop100Service
from apps.games.service.game_translation_services import (
    GameTranslationService,
    GameTranslationUnavailable,
)


class Command(BaseCommand):
    help = "전체/장르별 TOP100에 노출되는 게임 설명만 우선 한글로 번역합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--genre-id",
            type=int,
            nargs="*",
            help="번역 대상 장르 ID입니다. 미지정 시 0~14 전체 TOP100을 대상으로 합니다.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=20,
            help="이번 실행에서 번역할 최대 게임 수입니다.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="이미 저장된 한글 번역을 다시 생성합니다.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="번역하지 않고 대상 게임 개수와 일부 ID만 출력합니다.",
        )

    def handle(self, *args, **options):
        genre_ids = options["genre_id"] or list(range(0, 15))
        batch_size = options["batch_size"]
        overwrite = options["overwrite"]
        dry_run = options["dry_run"]

        if batch_size < 1:
            raise CommandError("--batch-size는 1 이상이어야 합니다.")

        invalid_genre_ids = [
            genre_id for genre_id in genre_ids if genre_id not in range(0, 15)
        ]
        if invalid_genre_ids:
            raise CommandError(f"유효하지 않은 genre_id 입니다: {invalid_genre_ids}")

        target_game_ids = self.collect_top100_game_ids(genre_ids)
        target_games = self.get_translation_targets(
            game_ids=target_game_ids,
            overwrite=overwrite,
        )

        self.stdout.write(
            f"TOP100 중복 제거 대상: {len(target_game_ids)}개, "
            f"번역 필요 대상: {len(target_games)}개"
        )

        if dry_run:
            preview_ids = [game.game_id for game in target_games[:batch_size]]
            self.stdout.write(f"이번 실행 예정 game_id: {preview_ids}")
            return

        translated = 0
        failed = 0

        for game in target_games[:batch_size]:
            updates = {}
            self.stdout.write(f"번역 중: {game.game_id} {game.name}")

            if (overwrite or not game.summary_ko) and game.summary:
                try:
                    updates["summary_ko"] = GameTranslationService.translate_text(
                        game.summary
                    )
                except GameTranslationUnavailable:
                    failed += 1
                    self.stdout.write(
                        self.style.WARNING(f"summary 번역 실패: {game.game_id}")
                    )

            if (overwrite or not game.storyline_ko) and game.storyline:
                try:
                    updates["storyline_ko"] = GameTranslationService.translate_text(
                        game.storyline
                    )
                except GameTranslationUnavailable:
                    failed += 1
                    self.stdout.write(
                        self.style.WARNING(f"storyline 번역 실패: {game.game_id}")
                    )

            if updates:
                for field, value in updates.items():
                    setattr(game, field, value)
                game.save(update_fields=list(updates.keys()))
                translated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"TOP100 번역 완료: translated={translated}, failed={failed}"
            )
        )

    def collect_top100_game_ids(self, genre_ids: list[int]) -> list[int]:
        seen_game_ids = set()
        target_game_ids = []

        for genre_id in genre_ids:
            games = GameTop100Service.get_top_100_games(genre_id=genre_id)
            self.stdout.write(f"genre_id={genre_id}: {len(games)}개 수집")

            for game in games:
                if game.game_id in seen_game_ids:
                    continue
                seen_game_ids.add(game.game_id)
                target_game_ids.append(game.game_id)

        return target_game_ids

    def get_translation_targets(
        self,
        *,
        game_ids: list[int],
        overwrite: bool,
    ) -> list[Game]:
        games_by_id = Game.objects.in_bulk(game_ids, field_name="game_id")
        target_games = []

        for game_id in game_ids:
            game = games_by_id.get(game_id)
            if game is None:
                continue
            if not self.has_translatable_source(game):
                continue
            if not overwrite and not self.needs_translation(game):
                continue
            target_games.append(game)

        return target_games

    @staticmethod
    def has_translatable_source(game: Game) -> bool:
        return bool((game.summary or "").strip() or (game.storyline or "").strip())

    @staticmethod
    def needs_translation(game: Game) -> bool:
        summary_needs_translation = bool((game.summary or "").strip()) and not bool(
            (game.summary_ko or "").strip()
        )
        storyline_needs_translation = bool((game.storyline or "").strip()) and not bool(
            (game.storyline_ko or "").strip()
        )

        return summary_needs_translation or storyline_needs_translation
