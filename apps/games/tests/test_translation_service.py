from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from apps.games.service.game_translation_services import (
    GameTranslationService,
    GameTranslationUnavailable,
)


class GameTranslationServiceTest(SimpleTestCase):
    def setUp(self):
        GameTranslationService._last_request_monotonic = None

    def test_suspicious_title_detection_flags_known_bad_outputs(self):
        self.assertTrue(
            GameTranslationService.is_suspicious_title_translation(
                "Metal: Hellsinger",
                "메탈:",
            )
        )
        self.assertTrue(
            GameTranslationService.is_suspicious_title_translation(
                "Resident Evil Requiem",
                "레지던트",
            )
        )
        self.assertTrue(
            GameTranslationService.is_suspicious_title_translation(
                "Hi-Fi Rush",
                "하이파이 러",
            )
        )
        self.assertTrue(
            GameTranslationService.is_suspicious_title_translation(
                "Dispatch",
                "디스패",
            )
        )

    def test_suspicious_title_detection_allows_valid_short_titles(self):
        self.assertFalse(
            GameTranslationService.is_suspicious_title_translation(
                "Crimson Desert",
                "붉은사막",
            )
        )
        self.assertFalse(
            GameTranslationService.is_suspicious_title_translation(
                "Sea of Stars",
                "별의 바다",
            )
        )
        self.assertFalse(
            GameTranslationService.is_suspicious_title_translation(
                "Ball x Pit",
                "볼 엑스 핏",
            )
        )
        self.assertFalse(
            GameTranslationService.is_suspicious_title_translation(
                "Still Wakes the Deep",
                "스틸 웨이크 더 딥",
            )
        )
        self.assertFalse(
            GameTranslationService.is_suspicious_title_translation(
                "Dispatch",
                "디스패치",
            )
        )

    @patch(
        "apps.games.service.game_translation_services."
        "GameTranslationService._request_translation"
    )
    def test_translate_title_retries_when_first_result_is_suspicious(
        self,
        mock_request_translation,
    ):
        mock_request_translation.side_effect = [
            "콜 오브 듀티",
            "콜 오브 듀티: 블랙 옵스 7",
        ]

        result = GameTranslationService.translate_title("Call of Duty: Black Ops 7")

        self.assertEqual(result, "콜 오브 듀티: 블랙 옵스 7")
        self.assertEqual(mock_request_translation.call_count, 2)

    @patch(
        "apps.games.service.game_translation_services."
        "GameTranslationService._request_translation"
    )
    def test_translate_title_raises_when_retry_stays_suspicious(
        self,
        mock_request_translation,
    ):
        mock_request_translation.side_effect = ["메탈:", "메탈:"]

        with self.assertRaises(GameTranslationUnavailable):
            GameTranslationService.translate_title("Metal: Hellsinger")

    @override_settings(
        GAME_TRANSLATION_GEMINI_API_KEY="test-key",
        GAME_TRANSLATION_GEMINI_MODEL="test-model",
        GAME_TRANSLATION_GEMINI_BASE_URL="https://example.com",
        GAME_TRANSLATION_GEMINI_TIMEOUT=1,
        GAME_TRANSLATION_MAX_ATTEMPTS=2,
        GAME_TRANSLATION_BACKOFF_SECONDS=0,
        GAME_TRANSLATION_RETRYABLE_MAX_ATTEMPTS=5,
        GAME_TRANSLATION_RETRYABLE_BACKOFF_SECONDS=0,
        GAME_TRANSLATION_MAX_BACKOFF_SECONDS=0,
        GAME_TRANSLATION_MIN_REQUEST_INTERVAL_SECONDS=0,
    )
    @patch("apps.games.service.game_translation_services.time.sleep")
    @patch("apps.games.service.game_translation_services.requests.post")
    def test_request_translation_retries_retryable_503_beyond_base_attempts(
        self,
        mock_post,
        mock_sleep,
    ):
        error_response = Mock(status_code=503, reason="Service Unavailable", headers={})
        error_response.raise_for_status.side_effect = requests.HTTPError(
            response=error_response
        )
        success_response = Mock(headers={})
        success_response.raise_for_status.return_value = None
        success_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "번역 결과"}]}}]
        }
        mock_post.side_effect = [error_response, error_response, success_response]

        result = GameTranslationService._request_translation(
            prompt="translate me",
            max_output_tokens=32,
            log_label="game title",
        )

        self.assertEqual(result, "번역 결과")
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 0)

    @override_settings(
        GAME_TRANSLATION_GEMINI_API_KEY="test-key",
        GAME_TRANSLATION_GEMINI_MODEL="test-model",
        GAME_TRANSLATION_GEMINI_BASE_URL="https://example.com",
        GAME_TRANSLATION_GEMINI_TIMEOUT=1,
        GAME_TRANSLATION_MAX_ATTEMPTS=2,
        GAME_TRANSLATION_BACKOFF_SECONDS=0,
        GAME_TRANSLATION_RETRYABLE_MAX_ATTEMPTS=5,
        GAME_TRANSLATION_RETRYABLE_BACKOFF_SECONDS=0,
        GAME_TRANSLATION_MAX_BACKOFF_SECONDS=0,
        GAME_TRANSLATION_MIN_REQUEST_INTERVAL_SECONDS=0,
    )
    @patch("apps.games.service.game_translation_services.time.sleep")
    @patch("apps.games.service.game_translation_services.requests.post")
    def test_request_translation_stops_non_retryable_400_at_base_attempts(
        self,
        mock_post,
        mock_sleep,
    ):
        error_response = Mock(status_code=400, reason="Bad Request", headers={})
        error_response.raise_for_status.side_effect = requests.HTTPError(
            response=error_response
        )
        mock_post.side_effect = [error_response, error_response, error_response]

        with self.assertRaises(GameTranslationUnavailable):
            GameTranslationService._request_translation(
                prompt="translate me",
                max_output_tokens=32,
                log_label="game title",
            )

        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 0)
