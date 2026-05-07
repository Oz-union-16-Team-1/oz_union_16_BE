import json
import logging
from typing import Generator

from apps.chatbot.models.models import ChatbotMessage, ChatbotSession
from apps.chatbot.services.chatbot_llm_services import (
    GeminiUnavailable,
    stream_answer,
)
from apps.chatbot.services.chatbot_sessions_services import build_session_payload

logger = logging.getLogger(__name__)

LLM_FAILURE_MESSAGE = (
    "응답을 생성하는 중 일시적인 오류가 발생했어요. 잠시 후 다시 질문해 주세요."
)

# Up to 20 turns (40 messages) of conversation history to send to Gemini.
HISTORY_MESSAGE_LIMIT = 40


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_gemini_contents(session: ChatbotSession) -> list[dict]:
    """Pull the most recent N messages for this session and convert them
    to Gemini's `contents` schema (role: user|model)."""
    recent = list(
        ChatbotMessage.objects.filter(session=session).order_by("-created_at")[
            :HISTORY_MESSAGE_LIMIT
        ]
    )
    recent.reverse()
    contents: list[dict] = []
    for message in recent:
        role = "model" if message.role == ChatbotMessage.Role.ASSISTANT else "user"
        contents.append({"role": role, "parts": [{"text": message.content}]})
    return contents


def generate_stream(
    session: ChatbotSession, question: str
) -> Generator[str, None, None]:
    session_payload = build_session_payload(session)

    yield format_sse("start", session_payload)

    contents = _build_gemini_contents(session)
    collected: list[str] = []

    try:
        for chunk in stream_answer(contents):
            collected.append(chunk)
            yield format_sse("chunk", {"content": chunk})
    except GeminiUnavailable:
        collected = [LLM_FAILURE_MESSAGE]
        yield format_sse("chunk", {"content": LLM_FAILURE_MESSAGE})
    except Exception:
        logger.exception("Unexpected error while streaming chatbot answer.")
        collected = [LLM_FAILURE_MESSAGE]
        yield format_sse("chunk", {"content": LLM_FAILURE_MESSAGE})

    full_response = "".join(collected).strip()
    if full_response:
        ChatbotMessage.objects.create(
            session=session,
            role=ChatbotMessage.Role.ASSISTANT,
            content=full_response,
        )

    yield format_sse("complete", session_payload)
