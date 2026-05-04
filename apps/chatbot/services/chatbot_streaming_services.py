import json
import time
from typing import Generator
from uuid import UUID

from django.core.cache import cache

from apps.chatbot.models.models import ChatbotSession
from apps.chatbot.services.chatbot_answer_builder_services import (
    build_answer,
    build_suggested_questions,
)
from apps.chatbot.services.chatbot_sessions_services import build_session_payload

STREAM_LOCK_TTL = 60


def _normalize_session_id(session_id: UUID | str) -> str:
    return str(session_id)


def _stream_lock_key(session_id: UUID | str) -> str:
    normalized_session_id = _normalize_session_id(session_id)
    return f"chatbot:streaming:{normalized_session_id}"


def acquire_stream_lock(session_id: UUID | str) -> bool:
    return cache.add(_stream_lock_key(session_id), True, timeout=STREAM_LOCK_TTL)


def release_stream_lock(session_id: UUID | str) -> None:
    cache.delete(_stream_lock_key(session_id))


def is_streaming(session_id: UUID | str) -> bool:
    return cache.get(_stream_lock_key(session_id)) is not None


def chunk_text(text: str, size: int = 6) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def generate_stream(
    session: ChatbotSession, question: str
) -> Generator[str, None, None]:
    answer = build_answer(question)
    suggested_questions = build_suggested_questions(question)
    session_payload = build_session_payload(session)

    yield format_sse("start", session_payload)

    for chunk in chunk_text(answer):
        yield format_sse("chunk", {"content": chunk})
        time.sleep(0.05)

    if suggested_questions:
        yield format_sse("suggestions", {"questions": suggested_questions})

    yield format_sse("complete", session_payload)
