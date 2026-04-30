from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.games.models import Game
from apps.games.service.game_translation_services import GameTranslationUnavailable


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
            name_ko="이미 번역된 제목",
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
        self.assertIn("번역 필요 대상: 2개", output)
        self.assertIn("이번 실행 예정 game_id: [3101, 3103]", output)

    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTranslationService.translate_text"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTranslationService.translate_title"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTop100Service.get_top_100_games"
    )
    def test_command_translates_only_batch_size(
        self,
        mock_top100,
        mock_translate_title,
        mock_translate_text,
    ):
        mock_top100.return_value = [self.game1, self.game2]
        mock_translate_title.side_effect = lambda text: f"KO-TITLE:{text}"
        mock_translate_text.side_effect = lambda text: f"KO:{text}"
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
        self.assertEqual(self.game1.name_ko, "KO-TITLE:Translate Target One")
        self.assertEqual(self.game1.summary_ko, "KO:First summary.")
        self.assertEqual(self.game1.storyline_ko, "KO:First storyline.")
        self.assertEqual(self.game2.name_ko, "이미 번역된 제목")
        self.assertEqual(self.game2.summary_ko, "이미 번역됨.")
        self.assertEqual(mock_translate_title.call_count, 1)
        self.assertEqual(mock_translate_text.call_count, 2)
        self.assertIn("TOP100 번역 완료: translated=1, failed=0", out.getvalue())

    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTranslationService.translate_text"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTranslationService.translate_title"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTop100Service.get_top_100_games"
    )
    def test_command_title_only_skips_description_translation(
        self,
        mock_top100,
        mock_translate_title,
        mock_translate_text,
    ):
        mock_top100.return_value = [self.game1]
        mock_translate_title.side_effect = lambda text: f"KO-TITLE:{text}"
        out = StringIO()

        call_command(
            "translate_top100_game_descriptions",
            "--genre-id",
            "0",
            "--batch-size",
            "1",
            "--title-only",
            stdout=out,
        )

        self.game1.refresh_from_db()
        self.assertEqual(self.game1.name_ko, "KO-TITLE:Translate Target One")
        self.assertFalse(self.game1.summary_ko)
        self.assertFalse(self.game1.storyline_ko)
        mock_translate_title.assert_called_once_with("Translate Target One")
        mock_translate_text.assert_not_called()

    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTranslationService.translate_text"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTranslationService.translate_title"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTop100Service.get_top_100_games"
    )
    def test_command_title_only_repairs_suspicious_existing_titles(
        self,
        mock_top100,
        mock_translate_title,
        mock_translate_text,
    ):
        self.game2.name = "Call of Duty: Black Ops 7"
        self.game2.name_ko = "콜 오브 듀티"
        self.game2.save(update_fields=["name", "name_ko"])
        mock_top100.return_value = [self.game2]
        mock_translate_title.return_value = "콜 오브 듀티: 블랙 옵스 7"

        call_command(
            "translate_top100_game_descriptions",
            "--genre-id",
            "0",
            "--batch-size",
            "1",
            "--title-only",
        )

        self.game2.refresh_from_db()
        self.assertEqual(self.game2.name_ko, "콜 오브 듀티: 블랙 옵스 7")
        mock_translate_title.assert_called_once_with("Call of Duty: Black Ops 7")
        mock_translate_text.assert_not_called()

    def test_command_rejects_invalid_genre_id(self):
        with self.assertRaises(CommandError):
            call_command(
                "translate_top100_game_descriptions",
                "--genre-id",
                "99",
            )

    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions.time.sleep"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTranslationService.translate_title"
    )
    @patch(
        "apps.games.management.commands.translate_top100_game_descriptions."
        "GameTop100Service.get_top_100_games"
    )
    def test_command_repeat_until_done_skips_failed_game_and_continues(
        self,
        mock_top100,
        mock_translate_title,
        mock_sleep,
    ):
        self.game2.name = "Second Target"
        self.game2.name_ko = None
        self.game2.save(update_fields=["name", "name_ko"])
        mock_top100.return_value = [self.game1, self.game2]

        def translate_side_effect(title):
            if title == "Translate Target One":
                raise GameTranslationUnavailable("503")
            return f"KO-TITLE:{title}"

        mock_translate_title.side_effect = translate_side_effect
        out = StringIO()

        call_command(
            "translate_top100_game_descriptions",
            "--genre-id",
            "0",
            "--batch-size",
            "1",
            "--title-only",
            "--repeat-until-done",
            "--max-batches",
            "2",
            stdout=out,
        )

        self.game1.refresh_from_db()
        self.game2.refresh_from_db()
        self.assertFalse(self.game1.name_ko)
        self.assertEqual(self.game2.name_ko, "KO-TITLE:Second Target")
        self.assertEqual(mock_translate_title.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 0)
        output = out.getvalue()
        self.assertIn(
            "TOP100 반복 번역 종료: batches=2, translated=1, failed=1", output
        )


class TranslateGameDescriptionsCommandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.game1 = Game.objects.create(
            game_id=4101,
            name="Escape from Tarkov",
            name_ko="이스케이프 프롬 타",
            slug="escape-from-tarkov",
            summary="Hardcore extraction shooter.",
            summary_ko="하드코어 익스트랙션 슈터.",
            storyline="Fight to escape Tarkov.",
            storyline_ko="타르코프에서 탈출하라.",
            first_release_date=timezone.now() - timezone.timedelta(days=1),
        )
        cls.game2 = Game.objects.create(
            game_id=4102,
            name="Missing Title Translation",
            slug="missing-title-translation",
            summary="Needs a Korean title.",
            first_release_date=timezone.now() - timezone.timedelta(days=1),
        )

    @patch(
        "apps.games.management.commands.translate_game_descriptions."
        "GameTranslationService.translate_text"
    )
    @patch(
        "apps.games.management.commands.translate_game_descriptions."
        "GameTranslationService.translate_title"
    )
    def test_command_title_only_overwrites_only_titles(
        self,
        mock_translate_title,
        mock_translate_text,
    ):
        mock_translate_title.return_value = "이스케이프 프롬 타르코프"

        call_command(
            "translate_game_descriptions",
            "--game-id",
            "4101",
            "--overwrite",
            "--title-only",
        )

        self.game1.refresh_from_db()
        self.assertEqual(self.game1.name_ko, "이스케이프 프롬 타르코프")
        self.assertEqual(self.game1.summary_ko, "하드코어 익스트랙션 슈터.")
        self.assertEqual(self.game1.storyline_ko, "타르코프에서 탈출하라.")
        mock_translate_title.assert_called_once_with("Escape from Tarkov")
        mock_translate_text.assert_not_called()

    @patch(
        "apps.games.management.commands.translate_game_descriptions."
        "GameTranslationService.translate_text"
    )
    @patch(
        "apps.games.management.commands.translate_game_descriptions."
        "GameTranslationService.translate_title"
    )
    def test_command_title_only_without_overwrite_translates_only_missing_titles(
        self,
        mock_translate_title,
        mock_translate_text,
    ):
        mock_translate_title.side_effect = [
            "이스케이프 프롬 타르코프",
            "누락된 제목 번역",
        ]

        call_command(
            "translate_game_descriptions",
            "--limit",
            "10",
            "--title-only",
        )

        self.game1.refresh_from_db()
        self.game2.refresh_from_db()
        self.assertEqual(self.game1.name_ko, "이스케이프 프롬 타르코프")
        self.assertEqual(self.game2.name_ko, "누락된 제목 번역")
        self.assertEqual(mock_translate_title.call_count, 2)
        mock_translate_title.assert_any_call("Escape from Tarkov")
        mock_translate_title.assert_any_call("Missing Title Translation")
        mock_translate_text.assert_not_called()
