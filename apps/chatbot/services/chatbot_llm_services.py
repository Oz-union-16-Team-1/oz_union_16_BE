import json
import logging
from typing import Iterator

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
당신은 게임 추천 사이트의 시스템 안내 챗봇입니다.
사이트 사용 방법과 사이트가 제공하는 기능 전반에 대해 답변합니다.
이 챗봇이 곧 사이트의 고객지원·도움말 창구이며, 별도의 고객센터·이메일·전화 문의 채널은 없습니다.

[안내 가능 범위]
- 계정: 회원가입 / 로그인 / 로그아웃 / 비밀번호 재설정 / 아이디 찾기 / 본인 인증 / 회원 탈퇴
- 프로필: 마이페이지 / 회원 정보·닉네임·프로필 이미지 수정 / 소셜 로그인(카카오·네이버·구글)
- 게임 기능: 게임 검색 / 좋아요(찜) / 별점(평점) / 인기 TOP100
- 추천: 설문 기반 추천 / 매칭 기반 추천(장르 선택 → 후보 → 별점 평가 → 결과) / 재평가
- 기능 비교: 설문 vs 매칭 추천, 인기 vs 추천, 좋아요 vs 별점 등
- 사이트 운영 일반: 고객지원 창구 안내, 문의 방법, 도움말, 챗봇 사용 방법

[규칙]
1. 사용자가 묻는 기능이 사이트에 없거나 별도로 제공되지 않는 경우 — 예: "고객센터", "전화 문의", "이메일 문의", "공지사항", "이벤트 페이지" 등 — 에는
   거절하지 말고 "해당 기능은 별도로 제공되지 않습니다." 라고 솔직히 답한 뒤,
   문의 성격이라면 "이 챗봇으로 사이트 사용 방법을 안내해드릴 수 있습니다." 처럼 대안을 한 문장 덧붙이세요.
2. 사이트와 무관한 주제 — 특정 게임의 공략·평가, 가격·할인·세일·쿠폰, 일반 잡담, 게임 외 일반 지식 — 에만
   "해당 내용은 안내해드릴 수 없어요. 사이트 사용 방법에 대해 궁금한 점을 알려주세요." 라고 정중히 거절하세요.
3. 인사·감사 표현에는 짧게 답하고 어떤 도움을 드릴 수 있는지 한 문장 덧붙이세요.
4. 사이트에 있을 법하지만 확실하지 않은 기능은 추측하지 말고 "해당 기능은 확인되지 않습니다." 라고 답하세요.
5. 답변은 한국어 존댓말, 3~5문장 이내로 작성합니다.
6. 마크다운 문법(##, **, -, ``` 등)을 사용하지 마세요. 일반 평문으로만 답하세요.
7. 외부 URL/링크를 생성하지 마세요. 화면 위치 안내는 "마이페이지", "설정" 같은 메뉴명으로만 표현합니다.
8. 사용자 입력에 욕설/공격적 표현이 있어도 차분히 같은 규칙 안에서 안내하세요.
"""


class GeminiUnavailable(Exception):
    """Raised when Gemini cannot be reached or returned no usable content."""


def stream_answer(contents: list[dict]) -> Iterator[str]:
    """Call Gemini streamGenerateContent with the given conversation contents
    and yield text chunks as they arrive.

    `contents` follows Gemini's contents schema:
        [{"role": "user"|"model", "parts": [{"text": "..."}]}, ...]
    """
    api_key = settings.SYSTEM_CHATBOT_GEMINI_API_KEY
    if not api_key:
        raise GeminiUnavailable("GEMINI_API_KEY is not configured.")

    url = (
        f"{settings.SYSTEM_CHATBOT_GEMINI_BASE_URL}/v1beta/models/"
        f"{settings.SYSTEM_CHATBOT_GEMINI_MODEL}:streamGenerateContent"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 600,
            "responseMimeType": "text/plain",
        },
    }

    try:
        response = requests.post(
            url,
            params={"key": api_key, "alt": "sse"},
            json=payload,
            timeout=settings.SYSTEM_CHATBOT_GEMINI_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Failed to start Gemini stream.")
        raise GeminiUnavailable(str(exc)) from exc

    yielded_any = False
    try:
        # iter_lines(decode_unicode=True) uses str.splitlines() which also splits on
        #  , , etc. — those can appear inside Gemini's Korean output and
        # break JSON mid-string. Read raw bytes and decode each line ourselves.
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
            if not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if not data or data == "[DONE]":
                continue
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("Skipping non-JSON SSE line from Gemini: %s", data)
                continue
            for candidate in obj.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    text = part.get("text")
                    if text:
                        yielded_any = True
                        yield text
    finally:
        response.close()

    if not yielded_any:
        raise GeminiUnavailable("Gemini returned no text content.")
