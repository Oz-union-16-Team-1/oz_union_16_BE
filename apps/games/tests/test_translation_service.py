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
                None,
                "번역",
            )
        )
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
        self.assertTrue(
            GameTranslationService.is_suspicious_title_translation(
                "The Legend of Heroes",
                "영웅전",
            )
        )
        self.assertTrue(
            GameTranslationService.is_suspicious_title_translation(
                "Final Fantasy Rebirth",
                "파판",
            )
        )
        self.assertTrue(
            GameTranslationService.is_suspicious_title_translation(
                "Resident Evil Requiem",
                "레지던트 이",
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
    def test_translate_text_returns_none_for_blank_and_translates_text(
        self,
        mock_request_translation,
    ):
        self.assertIsNone(GameTranslationService.translate_text(None))
        self.assertIsNone(GameTranslationService.translate_text(" "))

        mock_request_translation.return_value = "번역된 설명"

        result = GameTranslationService.translate_text(" English summary. ")

        self.assertEqual(result, "번역된 설명")
        mock_request_translation.assert_called_once()
        kwargs = mock_request_translation.call_args.kwargs
        self.assertIn("English summary.", kwargs["prompt"])
        self.assertIn("모든 문장을 빠짐없이 끝까지 번역", kwargs["prompt"])
        self.assertIn("반드시 완성된 한국어 문장으로 끝내", kwargs["prompt"])
        self.assertIn("요약하거나 생략하지 말고", kwargs["prompt"])
        self.assertEqual(kwargs["max_output_tokens"], 4096)
        self.assertEqual(kwargs["log_label"], "game description")

    @patch(
        "apps.games.service.game_translation_services."
        "GameTranslationService._request_translation"
    )
    def test_translate_title_returns_none_for_blank_and_retries_empty_candidate(
        self,
        mock_request_translation,
    ):
        self.assertIsNone(GameTranslationService.translate_title(None))
        self.assertIsNone(GameTranslationService.translate_title(""))

        mock_request_translation.side_effect = [None, "디스패치"]

        result = GameTranslationService.translate_title("Dispatch")

        self.assertEqual(result, "디스패치")
        self.assertEqual(mock_request_translation.call_count, 2)

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

    @override_settings(GAME_TRANSLATION_GEMINI_API_KEY="")
    def test_request_translation_raises_when_api_key_missing(self):
        with self.assertRaises(GameTranslationUnavailable):
            GameTranslationService._request_translation(
                prompt="translate me",
                max_output_tokens=32,
                log_label="game title",
            )

    @override_settings(
        GAME_TRANSLATION_GEMINI_API_KEY="test-key",
        GAME_TRANSLATION_GEMINI_MODEL="test-model",
        GAME_TRANSLATION_GEMINI_BASE_URL="https://example.com",
        GAME_TRANSLATION_GEMINI_TIMEOUT=1,
        GAME_TRANSLATION_MAX_ATTEMPTS=1,
        GAME_TRANSLATION_BACKOFF_SECONDS=0,
        GAME_TRANSLATION_RETRYABLE_MAX_ATTEMPTS=1,
        GAME_TRANSLATION_MIN_REQUEST_INTERVAL_SECONDS=0,
    )
    @patch("apps.games.service.game_translation_services.requests.post")
    def test_request_translation_raises_when_response_text_is_empty(self, mock_post):
        response = Mock(headers={})
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "  "}]}}]
        }
        mock_post.return_value = response

        with self.assertRaises(GameTranslationUnavailable):
            GameTranslationService._request_translation(
                prompt="translate me",
                max_output_tokens=32,
                log_label="game title",
            )

    @patch(
        "apps.games.service.game_translation_services."
        "GameTranslationService.translate_text"
    )
    def test_translate_descriptions_delegates_each_description(self, mock_translate):
        mock_translate.side_effect = ["요약", "스토리"]

        result = GameTranslationService.translate_descriptions(
            summary="summary",
            storyline="storyline",
        )

        self.assertEqual(result, {"summary_ko": "요약", "storyline_ko": "스토리"})
        self.assertEqual(mock_translate.call_count, 2)

    def test_format_error_handles_request_errors_and_plain_errors(self):
        response = Mock(status_code=429, reason="Too Many Requests")
        http_error = requests.HTTPError(response=response)
        self.assertEqual(
            GameTranslationService._format_error(http_error),
            "HTTP 429 Too Many Requests",
        )

        request_error_with_response = requests.RequestException()
        request_error_with_response.response = Mock(
            status_code=504,
            reason="Gateway Timeout",
        )
        self.assertEqual(
            GameTranslationService._format_error(request_error_with_response),
            "HTTP 504 Gateway Timeout",
        )
        self.assertEqual(
            GameTranslationService._format_error(requests.Timeout()),
            "Timeout",
        )
        self.assertEqual(
            GameTranslationService._format_error(ValueError("bad payload")),
            "bad payload",
        )

    @override_settings(GAME_TRANSLATION_MIN_REQUEST_INTERVAL_SECONDS=2)
    @patch("apps.games.service.game_translation_services.time.sleep")
    @patch("apps.games.service.game_translation_services.time.monotonic")
    def test_wait_for_request_slot_sleeps_until_min_interval(
        self,
        mock_monotonic,
        mock_sleep,
    ):
        mock_monotonic.side_effect = [10.0, 10.5, 12.0]

        GameTranslationService._wait_for_request_slot()
        GameTranslationService._wait_for_request_slot()

        mock_sleep.assert_called_once_with(1.5)
        self.assertEqual(GameTranslationService._last_request_monotonic, 12.0)

    def test_retryable_exception_detection_branches(self):
        self.assertFalse(GameTranslationService._is_retryable_exception(ValueError()))

        retryable_response = Mock(status_code=503)
        self.assertTrue(
            GameTranslationService._is_retryable_exception(
                requests.HTTPError(response=retryable_response)
            )
        )

        non_retryable_response = Mock(status_code=400)
        self.assertFalse(
            GameTranslationService._is_retryable_exception(
                requests.RequestException(response=non_retryable_response)
            )
        )
        self.assertTrue(
            GameTranslationService._is_retryable_exception(requests.ConnectionError())
        )

    @override_settings(
        GAME_TRANSLATION_BACKOFF_SECONDS=1,
        GAME_TRANSLATION_RETRYABLE_BACKOFF_SECONDS=3,
        GAME_TRANSLATION_MAX_BACKOFF_SECONDS=5,
    )
    def test_retry_delay_uses_retry_after_and_max_backoff(self):
        response = Mock(headers={"Retry-After": "4"})
        error = requests.HTTPError(response=response)

        retryable_delay = GameTranslationService._retry_delay_seconds(
            error,
            1,
            retryable=True,
        )
        non_retryable_delay = GameTranslationService._retry_delay_seconds(
            requests.Timeout(),
            2,
            retryable=False,
        )

        self.assertEqual(retryable_delay, 5)
        self.assertEqual(non_retryable_delay, 4)

    def test_retry_after_seconds_handles_missing_and_invalid_headers(self):
        self.assertIsNone(
            GameTranslationService._retry_after_seconds(requests.Timeout())
        )
        self.assertIsNone(
            GameTranslationService._retry_after_seconds(
                requests.HTTPError(response=Mock(headers={}))
            )
        )
        self.assertIsNone(
            GameTranslationService._retry_after_seconds(
                requests.HTTPError(response=Mock(headers={"Retry-After": "soon"}))
            )
        )
        self.assertEqual(
            GameTranslationService._retry_after_seconds(
                requests.HTTPError(response=Mock(headers={"Retry-After": "-1"}))
            ),
            0.0,
        )

    def test_build_title_prompt_and_normalize_title_helpers(self):
        prompt = GameTranslationService._build_title_prompt(
            "Dispatch",
            suspicious_title="디스패",
        )

        self.assertIn("직전 번역 후보: 디스패", prompt)
        self.assertIn("Dispatch", prompt)
        self.assertIsNone(GameTranslationService._normalize_title(123))
        self.assertEqual(
            GameTranslationService._normalize_title('"디스패치"'), "디스패치"
        )

    def test_extract_text_joins_only_non_blank_text_parts(self):
        payload = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": " 첫 번째 "},
                            {"text": " "},
                            "invalid",
                            {"text": "두 번째"},
                        ]
                    }
                }
            ]
        }

        self.assertEqual(
            GameTranslationService._extract_text(payload), "첫 번째\n두 번째"
        )
