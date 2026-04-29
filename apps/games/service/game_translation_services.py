import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GameTranslationUnavailable(Exception):
    """게임 설명 번역을 생성할 수 없을 때 발생하는 예외입니다."""


class GameTranslationService:
    @staticmethod
    def translate_text(text: str | None) -> str | None:
        if not isinstance(text, str) or not text.strip():
            return None

        api_key = settings.GAME_TRANSLATION_GEMINI_API_KEY
        if not api_key:
            raise GameTranslationUnavailable("번역 API 키가 설정되지 않았습니다.")

        url = (
            f"{settings.GAME_TRANSLATION_GEMINI_BASE_URL}/v1beta/models/"
            f"{settings.GAME_TRANSLATION_GEMINI_MODEL}:generateContent"
        )
        prompt = (
            "다음 영어 게임 설명을 자연스러운 한국어로 번역해 주세요.\n"
            "게임명, 인명, 지명, 고유명사는 억지로 번역하지 말고 자연스럽게 유지해 주세요.\n"
            "설명문만 반환하고, 해설이나 따옴표는 붙이지 마세요.\n\n"
            f"{text.strip()}"
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
                "maxOutputTokens": 2048,
            },
        }

        last_error: Exception | None = None
        for attempt in range(settings.GAME_TRANSLATION_MAX_ATTEMPTS):
            try:
                response = requests.post(
                    url=url,
                    params={"key": api_key},
                    json=payload,
                    timeout=settings.GAME_TRANSLATION_GEMINI_TIMEOUT,
                )
                response.raise_for_status()
                translated_text = GameTranslationService._extract_text(response.json())
                break
            except (
                KeyError,
                TypeError,
                ValueError,
                requests.RequestException,
            ) as exc:
                last_error = exc
                logger.warning("Failed to translate game description: %s", exc)
                if attempt < settings.GAME_TRANSLATION_MAX_ATTEMPTS - 1:
                    time.sleep(settings.GAME_TRANSLATION_BACKOFF_SECONDS * (2**attempt))
                    continue
                raise GameTranslationUnavailable(
                    "게임 설명 번역에 실패했습니다."
                ) from exc
        else:
            raise GameTranslationUnavailable(
                "게임 설명 번역에 실패했습니다."
            ) from last_error

        if not translated_text:
            raise GameTranslationUnavailable("게임 설명 번역 결과가 비어 있습니다.")

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
