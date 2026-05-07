import logging
import re
import threading
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GameTranslationUnavailable(Exception):
    """게임 번역을 생성할 수 없을 때 발생하는 예외입니다."""


class GameTranslationService:
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    TITLE_RETRY_ATTEMPTS = 2
    TITLE_STOPWORDS = {
        "a",
        "an",
        "and",
        "at",
        "edition",
        "for",
        "from",
        "game",
        "in",
        "of",
        "on",
        "the",
        "to",
        "ver",
        "vs",
        "with",
    }
    TITLE_TRAILING_PUNCTUATION = (":", "-", "/", "(", "[", "{")
    _REQUEST_LOCK = threading.Lock()
    _last_request_monotonic: float | None = None

    @staticmethod
    def translate_text(text: str | None) -> str | None:
        if not isinstance(text, str) or not text.strip():
            return None

        prompt = (
            "다음 영어 게임 설명을 자연스러운 한국어로 번역해 주세요.\n"
            "게임명, 인명, 지명, 고유명사는 억지로 번역하지 말고 자연스럽게 유지해 주세요.\n"
            "원문의 모든 문장을 빠짐없이 끝까지 번역해 주세요.\n"
            "문장을 중간에 끊지 말고, 반드시 완성된 한국어 문장으로 끝내 주세요.\n"
            "출력이 길어도 요약하거나 생략하지 말고 원문의 정보량을 유지해 주세요.\n"
            "설명문만 반환하고, 해설이나 따옴표는 붙이지 마세요.\n\n"
            f"{text.strip()}"
        )
        return GameTranslationService._request_translation(
            prompt=prompt,
            max_output_tokens=4096,
            log_label="game description",
        )

    @classmethod
    def translate_title(cls, title: str | None) -> str | None:
        if not isinstance(title, str) or not title.strip():
            return None

        normalized_title = title.strip()
        suspicious_title: str | None = None

        for attempt in range(cls.TITLE_RETRY_ATTEMPTS):
            translated_title = cls._request_translation(
                prompt=cls._build_title_prompt(
                    normalized_title,
                    suspicious_title=suspicious_title,
                ),
                max_output_tokens=512,
                log_label="game title",
            )
            if translated_title is None:
                continue

            cleaned_title = cls._normalize_title(translated_title)
            if not cls.is_suspicious_title_translation(
                normalized_title,
                cleaned_title,
            ):
                return cleaned_title

            suspicious_title = cleaned_title
            logger.warning(
                "Suspicious translated title detected for %r: %r",
                normalized_title,
                cleaned_title,
            )

        raise GameTranslationUnavailable("게임 제목 번역 결과가 불완전합니다.")

    @classmethod
    def _request_translation(
        cls,
        *,
        prompt: str,
        max_output_tokens: int,
        log_label: str,
    ) -> str:
        api_key = settings.GAME_TRANSLATION_GEMINI_API_KEY
        if not api_key:
            raise GameTranslationUnavailable("번역 API 키가 설정되지 않았습니다.")

        url = (
            f"{settings.GAME_TRANSLATION_GEMINI_BASE_URL}/v1beta/models/"
            f"{settings.GAME_TRANSLATION_GEMINI_MODEL}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_output_tokens,
            },
        }

        last_error: Exception | None = None
        base_attempts = max(settings.GAME_TRANSLATION_MAX_ATTEMPTS, 1)
        retryable_attempts = max(
            base_attempts,
            getattr(settings, "GAME_TRANSLATION_RETRYABLE_MAX_ATTEMPTS", base_attempts),
        )
        for attempt in range(retryable_attempts):
            try:
                cls._wait_for_request_slot()
                response = requests.post(
                    url=url,
                    params={"key": api_key},
                    json=payload,
                    timeout=settings.GAME_TRANSLATION_GEMINI_TIMEOUT,
                )
                response.raise_for_status()
                translated_text = cls._extract_text(response.json())
                break
            except (
                KeyError,
                TypeError,
                ValueError,
                requests.RequestException,
            ) as exc:
                last_error = exc
                is_retryable = cls._is_retryable_exception(exc)
                allowed_attempts = retryable_attempts if is_retryable else base_attempts
                logger.warning(
                    "Failed to translate %s: %s",
                    log_label,
                    cls._format_error(exc),
                )
                if attempt < allowed_attempts - 1:
                    delay = cls._retry_delay_seconds(
                        exc, attempt, retryable=is_retryable
                    )
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise GameTranslationUnavailable("게임 번역에 실패했습니다.") from exc
        else:
            raise GameTranslationUnavailable(
                "게임 번역에 실패했습니다."
            ) from last_error

        if not translated_text:
            raise GameTranslationUnavailable("게임 번역 결과가 비어 있습니다.")

        return translated_text

    @staticmethod
    def translate_descriptions(
        *,
        summary: str | None,
        storyline: str | None,
    ) -> dict[str, str | None]:
        return {
            "summary_ko": GameTranslationService.translate_text(summary),
            "storyline_ko": GameTranslationService.translate_text(storyline),
        }

    @classmethod
    def is_suspicious_title_translation(
        cls,
        original_title: str | None,
        translated_title: str | None,
    ) -> bool:
        normalized_original = cls._normalize_title(original_title)
        normalized_translated = cls._normalize_title(translated_title)
        if not normalized_original or not normalized_translated:
            return True

        compact_translated = re.sub(r"\s+", "", normalized_translated)
        if not compact_translated:
            return True

        if normalized_translated.endswith(cls.TITLE_TRAILING_PUNCTUATION):
            return True

        raw_english_tokens = re.findall(r"[A-Za-z0-9]+", normalized_original)
        english_tokens = [
            token
            for token in raw_english_tokens
            if token.casefold() not in cls.TITLE_STOPWORDS
            and (len(token) > 1 or token.isdigit())
        ]
        has_stopword = any(
            token.casefold() in cls.TITLE_STOPWORDS for token in raw_english_tokens
        )
        compact_length = len(compact_translated)
        last_token = normalized_translated.split()[-1]
        last_english_token = raw_english_tokens[-1] if raw_english_tokens else ""
        last_english_token_lower = last_english_token.casefold()
        has_subtitle_separator = any(
            separator in normalized_original for separator in (":", " - ", " – ", " — ")
        )

        if has_subtitle_separator and compact_length <= 5:
            return True

        if len(english_tokens) >= 4 and compact_length <= 5:
            return True

        if len(english_tokens) >= 3 and compact_length <= 4:
            return True

        if (
            len(raw_english_tokens) >= 3
            and len(last_token) == 1
            and not last_token.isdigit()
            and len(last_english_token) >= 4
            and (compact_length <= 6 or (len(raw_english_tokens) == 3 and has_stopword))
        ):
            return True

        if (
            len(raw_english_tokens) >= 3
            and " " not in normalized_translated
            and compact_length <= 5
        ):
            return True

        if last_english_token_lower.endswith(
            ("ch", "tch")
        ) and not compact_translated.endswith("치"):
            return True

        return False

    @staticmethod
    def _format_error(exc: Exception) -> str:
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            status_code = exc.response.status_code
            reason = exc.response.reason or ""
            return f"HTTP {status_code} {reason}".strip()

        if isinstance(exc, requests.RequestException):
            response = getattr(exc, "response", None)
            if response is not None:
                status_code = response.status_code
                reason = response.reason or ""
                return f"HTTP {status_code} {reason}".strip()
            return exc.__class__.__name__

        return str(exc)

    @classmethod
    def _wait_for_request_slot(cls) -> None:
        min_interval = max(
            float(
                getattr(
                    settings,
                    "GAME_TRANSLATION_MIN_REQUEST_INTERVAL_SECONDS",
                    0,
                )
            ),
            0.0,
        )
        if min_interval <= 0:
            return

        with cls._REQUEST_LOCK:
            now = time.monotonic()
            if cls._last_request_monotonic is not None:
                remaining = min_interval - (now - cls._last_request_monotonic)
                if remaining > 0:
                    time.sleep(remaining)
                    now = time.monotonic()
            cls._last_request_monotonic = now

    @classmethod
    def _is_retryable_exception(cls, exc: Exception) -> bool:
        if isinstance(exc, (KeyError, TypeError, ValueError)):
            return False

        if isinstance(exc, requests.HTTPError):
            response = exc.response
            return bool(
                response is not None
                and response.status_code in cls.RETRYABLE_STATUS_CODES
            )

        if isinstance(exc, requests.RequestException):
            response = getattr(exc, "response", None)
            if response is None:
                return True
            return response.status_code in cls.RETRYABLE_STATUS_CODES

        return False

    @classmethod
    def _retry_delay_seconds(
        cls,
        exc: Exception,
        attempt: int,
        *,
        retryable: bool,
    ) -> float:
        if retryable:
            base_delay = max(
                float(settings.GAME_TRANSLATION_BACKOFF_SECONDS),
                float(
                    getattr(
                        settings,
                        "GAME_TRANSLATION_RETRYABLE_BACKOFF_SECONDS",
                        settings.GAME_TRANSLATION_BACKOFF_SECONDS,
                    )
                ),
            )
        else:
            base_delay = max(float(settings.GAME_TRANSLATION_BACKOFF_SECONDS), 0.0)

        retry_after = cls._retry_after_seconds(exc)
        computed_delay = base_delay * (2**attempt)
        delay = max(computed_delay, retry_after or 0.0)
        max_backoff = max(
            float(getattr(settings, "GAME_TRANSLATION_MAX_BACKOFF_SECONDS", delay)),
            0.0,
        )
        return min(delay, max_backoff) if max_backoff else delay

    @staticmethod
    def _retry_after_seconds(exc: Exception) -> float | None:
        response = None
        if isinstance(exc, requests.HTTPError):
            response = exc.response
        elif isinstance(exc, requests.RequestException):
            response = getattr(exc, "response", None)

        if response is None:
            return None

        retry_after = response.headers.get("Retry-After")
        if retry_after is None:
            return None

        try:
            return max(float(retry_after), 0.0)
        except TypeError, ValueError:
            return None

    @staticmethod
    def _build_title_prompt(
        title: str,
        *,
        suspicious_title: str | None = None,
    ) -> str:
        prompt_lines = [
            "다음 영어 게임 제목을 한국어 표시명으로 번역해 주세요.",
            "공식 한국어 제목이 널리 쓰이면 그 표기를 우선 사용해 주세요.",
            "공식 한국어 제목이 불분명하면 자연스럽게 음역하거나 번역해 주세요.",
            "제목의 일부만 줄이거나 생략하지 말고 마지막 단어까지 모두 포함해 주세요.",
            "고유명사와 지명은 빠뜨리지 말고 자연스럽게 유지해 주세요.",
            "부제목, 숫자, 콜론(:) 뒤의 내용도 빠짐없이 반영해 주세요.",
            "원문 영어 제목을 괄호로 붙이지 말고, 한국어 제목만 반환해 주세요.",
            "해설, 따옴표, 마침표는 붙이지 마세요.",
        ]
        if suspicious_title:
            prompt_lines.extend(
                [
                    "",
                    "직전 번역 후보가 축약되었거나 중간에 끊긴 것으로 보입니다.",
                    f"직전 번역 후보: {suspicious_title}",
                    "이번에는 제목 전체를 끝까지 번역해 주세요.",
                ]
            )

        prompt_lines.extend(["", title])
        return "\n".join(prompt_lines)

    @staticmethod
    def _normalize_title(value: str | None) -> str | None:
        if not isinstance(value, str):
            return None

        stripped = value.strip().strip('"').strip("'").strip()
        return stripped or None

    @staticmethod
    def _extract_text(payload: dict) -> str:
        parts = payload["candidates"][0]["content"]["parts"]
        texts = []

        for part in parts:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())

        return "\n".join(texts).strip()
