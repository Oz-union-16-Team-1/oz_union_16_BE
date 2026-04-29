from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.games.models import Game


class TranslateTop100GameDescriptionsCommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.game1 = Game.objects.create(
            game_id=3101,
            name="Translate Target One",
            slug="translate-target-one",
            summary="First summary.",
            storyline="First storyline.",
            first_release_date=timezone.now() - timezone.timedelta(days=1),
        )
        cls.game2 = Game.objects.create(
            game_id=3102,
            name="Already Translated",
            slug="already-translated",
            summary="Second summary.",
            summary_ko="이미 번역됨.",
            first_release_date=timezone.now() - timezone.timedelta(days=1),
        )
        cls.game3 = Game.objects.create(
            game_id=3103,
            name="No Description",
            slug="no-description",
            first_release_date=timezone.now() - timezone.timedelta(days=1),
        )

    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTop100Service.get_top_100_games"
    )
    def test_dry_run_collects_unique_translation_targets(self, mock_top100):
        mock_top100.side_effect = [
            [self.game1, self.game2],
            [self.game1, self.game3],
        ]
        out = StringIO()

        call_command(
            "translate_top100_game_descriptions",
            "--genre-id",
            "0",
            "3",
            "--batch-size",
            "2",
            "--dry-run",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("TOP100 중복 제거 대상: 3개", output)
        self.assertIn("번역 필요 대상: 1개", output)
        self.assertIn("이번 실행 예정 game_id: [3101]", output)

    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTranslationService.translate_text"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTop100Service.get_top_100_games"
    )
    def test_command_translates_only_batch_size(self, mock_top100, mock_translate):
        mock_top100.return_value = [self.game1, self.game2]
        mock_translate.side_effect = lambda text: f"KO:{text}"
        out = StringIO()

        call_command(
            "translate_top100_game_descriptions",
            "--genre-id",
            "0",
            "--batch-size",
            "1",
            stdout=out,
        )

        self.game1.refresh_from_db()
        self.game2.refresh_from_db()
        self.assertEqual(self.game1.summary_ko, "KO:First summary.")
        self.assertEqual(self.game1.storyline_ko, "KO:First storyline.")
        self.assertEqual(self.game2.summary_ko, "이미 번역됨.")
        self.assertEqual(mock_translate.call_count, 2)
        self.assertIn("TOP100 번역 완료: translated=1, failed=0", out.getvalue())

    def test_command_rejects_invalid_genre_id(self):
        with self.assertRaises(CommandError):
            call_command(
                "translate_top100_game_descriptions",
                "--genre-id",
                "99",
            )
