from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.games.models import Game
from apps.games.service.game_translation_services import (
    GameTranslationService,
    GameTranslationUnavailable,
)


class Command(BaseCommand):
    help = "기존 게임 제목/설명(name/summary/storyline)을 한글로 번역하여 저장합니다."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--offset", type=int, default=0)
        parser.add_argument("--game-id", type=int, nargs="*")
        parser.add_argument("--overwrite", action="store_true")
        parser.add_argument(
            "--title-only",
            action="store_true",
            help="게임 제목(name_ko)만 번역하고 설명 번역은 건너뜁니다.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        offset = options["offset"]
        game_ids = options["game_id"]
        overwrite = options["overwrite"]
        title_only = options["title_only"]

        queryset = Game.objects.filter(Q(name__isnull=False)).order_by("game_id")
        if not title_only:
            queryset = Game.objects.filter(
                Q(name__isnull=False)
                | Q(summary__isnull=False)
                | Q(storyline__isnull=False)
            ).order_by("game_id")

        if game_ids:
            queryset = queryset.filter(game_id__in=game_ids)

        if not overwrite:
            missing_title_translation = (
                Q(name__isnull=False)
                & ~Q(name="")
                & (Q(name_ko__isnull=True) | Q(name_ko=""))
            )
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
            if title_only:
                queryset = queryset
            else:
                queryset = queryset.filter(
                    missing_title_translation
                    | missing_summary_translation
                    | missing_storyline_translation
                )

        queryset = queryset[offset : offset + limit]

        translated = 0
        failed = 0

        for game in queryset.iterator():
            updates = {}
            self.stdout.write(f"번역 중: {game.game_id} {game.name}")

            should_translate_title = bool((game.name or "").strip()) and (
                overwrite
                or not (game.name_ko or "").strip()
                or GameTranslationService.is_suspicious_title_translation(
                    game.name,
                    game.name_ko,
                )
            )
            if should_translate_title:
                try:
                    updates["name_ko"] = GameTranslationService.translate_title(
                        game.name
                    )
                except GameTranslationUnavailable:
                    failed += 1
                    self.stdout.write(
                        self.style.WARNING(f"title 번역 실패: {game.game_id}")
                    )

            if not title_only and (overwrite or not game.summary_ko) and game.summary:
                try:
                    updates["summary_ko"] = GameTranslationService.translate_text(
                        game.summary
                    )
                except GameTranslationUnavailable:
                    failed += 1
                    self.stdout.write(
                        self.style.WARNING(f"summary 번역 실패: {game.game_id}")
                    )

            if (
                not title_only
                and (overwrite or not game.storyline_ko)
                and game.storyline
            ):
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
