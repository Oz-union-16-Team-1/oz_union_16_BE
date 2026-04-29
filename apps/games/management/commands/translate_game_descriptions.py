from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.games.models import Game
from apps.games.service.game_translation_services import (
    GameTranslationService,
    GameTranslationUnavailable,
)


class Command(BaseCommand):
    help = "기존 게임 설명(summary/storyline)을 한글로 번역하여 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--game-id", type=int, nargs="*")
        parser.add_argument("--overwrite", action="store_true")

    def handle(self, *args, **options):
        limit = options["limit"]
        offset = options["offset"]
        game_ids = options["game_id"]
        overwrite = options["overwrite"]

        queryset = Game.objects.filter(
            Q(summary__isnull=False) | Q(storyline__isnull=False)
        ).order_by("game_id")

        if game_ids:
            queryset = queryset.filter(game_id__in=game_ids)

        if not overwrite:
            missing_summary_translation = (
                Q(summary__isnull=False)
                & ~Q(summary="")
                & (Q(summary_ko__isnull=True) | Q(summary_ko=""))
            )
            missing_storyline_translation = (
                Q(storyline__isnull=False)
                & ~Q(storyline="")
                & (Q(storyline_ko__isnull=True) | Q(storyline_ko=""))
            )
            queryset = queryset.filter(
                missing_summary_translation | missing_storyline_translation
            )

        queryset = queryset[offset : offset + limit]

        translated = 0
        failed = 0

        for game in queryset.iterator():
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
            self.style.SUCCESS(f"번역 완료: translated={translated}, failed={failed}")
        )
