import json
import time
from datetime import timedelta
from typing import Generator

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.chatbot.models.models import ChatbotSession


SESSION_EXPIRE_MINUTES = 30
QUESTION_CACHE_TTL = 60 * 30
STREAM_LOCK_TTL = 60


def _question_cache_key(session_id: int) -> str:
    return f"chatbot:question:{session_id}"


def _stream_lock_key(session_id: int) -> str:
    return f"chatbot:streaming:{session_id}"


@transaction.atomic
def create_chatbot_session() -> ChatbotSession:
    return ChatbotSession.objects.create(
        session_type=ChatbotSession.SessionTypeChoices.CHATBOT,
        expires_at=timezone.now() + timedelta(minutes=SESSION_EXPIRE_MINUTES),
    )


def get_valid_chatbot_session(session_id: int) -> ChatbotSession | None:
    try:
        session = ChatbotSession.objects.get(pk=session_id)
    except ChatbotSession.DoesNotExist:
        return None

    if session.session_type != ChatbotSession.SessionTypeChoices.CHATBOT:
        return None

    if session.is_expired:
        return None

    return session


def save_question_to_cache(session_id: int, message: str) -> None:
    cache.set(_question_cache_key(session_id), message, timeout=QUESTION_CACHE_TTL)


def get_question_from_cache(session_id: int) -> str | None:
    return cache.get(_question_cache_key(session_id))


def delete_question_from_cache(session_id: int) -> None:
    cache.delete(_question_cache_key(session_id))


def acquire_stream_lock(session_id: int) -> bool:
    return cache.add(_stream_lock_key(session_id), True, timeout=STREAM_LOCK_TTL)


def release_stream_lock(session_id: int) -> None:
    cache.delete(_stream_lock_key(session_id))


def is_streaming(session_id: int) -> bool:
    return cache.get(_stream_lock_key(session_id)) is not None


def build_answer(message: str) -> str:
    """
    실제 LLM 연동 전 임시 답변.
    나중에 OpenAI/Gemini 연동 시 이 함수만 교체하면 됨.
    """
    normalized = message.strip()

    if "아이디" in normalized and "찾" in normalized:
        return "아이디는 본인 인증을 통해 찾을 수 있습니다."
    if "비밀번호" in normalized:
        return "비밀번호는 비밀번호 찾기 기능을 통해 재설정할 수 있습니다."
    if "게임" in normalized and "안나와요" in normalized:
        return "게임이 검색되지 않는 경우 정확한 게임명 또는 유사한 검색어로 다시 시도해 주세요."
    if "할인" in normalized:
        return "할인 여부는 게임 상세 페이지나 스토어 정보를 통해 확인할 수 있습니다."
    if "계정 삭제" in normalized:
        return "계정 삭제는 마이페이지의 회원 탈퇴 메뉴에서 진행할 수 있습니다."

    return "문의하신 내용을 확인했습니다. 조금 더 구체적으로 입력해 주시면 더 정확하게 안내해드릴 수 있습니다."


def chunk_text(text: str, size: int = 6) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def generate_stream(session_id: int, question: str) -> Generator[str, None, None]:
    answer = build_answer(question)

    yield format_sse("start", {"session_id": session_id})

    for chunk in chunk_text(answer):
        yield format_sse("chunk", {"content": chunk})
        time.sleep(0.05)

    yield format_sse("complete", {"session_id": session_id})