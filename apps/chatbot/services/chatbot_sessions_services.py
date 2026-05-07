import math
from datetime import timedelta
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.chatbot.models.models import ChatbotMessage, ChatbotSession

SESSION_EXPIRE_MINUTES = 30
SESSION_TTL_SECONDS = SESSION_EXPIRE_MINUTES * 60


@transaction.atomic
def create_chatbot_session() -> ChatbotSession:
    return ChatbotSession.objects.create(
        expires_at=timezone.now() + timedelta(seconds=SESSION_TTL_SECONDS),
    )


def get_valid_chatbot_session(session_id: UUID | str) -> ChatbotSession | None:
    try:
        session = ChatbotSession.objects.get(pk=session_id)
    except ChatbotSession.DoesNotExist, ValidationError, ValueError:
        return None

    if session.is_expired:
        return None

    session.expires_at = timezone.now() + timedelta(seconds=SESSION_TTL_SECONDS)
    session.save(update_fields=["expires_at"])

    return session


def claim_pending_question(
    session_id: UUID | str,
) -> tuple[ChatbotSession | None, str | None]:
    """Atomically pop the pending question for a session.

    Returns (session, question):
        - (None, None)     : session not found / expired / invalid id
        - (session, None)  : session valid but no pending question
        - (session, str)   : claimed; pending_question cleared and TTL rolled
    """
    with transaction.atomic():
        try:
            session = ChatbotSession.objects.select_for_update().get(pk=session_id)
        except ChatbotSession.DoesNotExist, ValidationError, ValueError:
            return None, None

        if session.is_expired:
            return None, None

        question = session.pending_question
        if question is None:
            return session, None

        session.pending_question = None
        session.expires_at = timezone.now() + timedelta(seconds=SESSION_TTL_SECONDS)
        session.save(update_fields=["pending_question", "expires_at"])
        ChatbotMessage.objects.create(
            session=session,
            role=ChatbotMessage.Role.USER,
            content=question,
        )
        return session, question


def get_chatbot_session(session_id: UUID | str) -> ChatbotSession | None:
    try:
        return ChatbotSession.objects.get(pk=session_id)
    except ChatbotSession.DoesNotExist:
        return None


def get_session_expires_in_seconds(session: ChatbotSession) -> int:
    remaining_seconds = (session.expires_at - timezone.now()).total_seconds()
    return max(0, math.ceil(remaining_seconds))


def build_session_payload(session: ChatbotSession) -> dict:
    return {
        "session_id": str(session.pk),
        "expires_at": session.expires_at.isoformat(),
        "expires_in_seconds": get_session_expires_in_seconds(session),
        "session_ttl_seconds": SESSION_TTL_SECONDS,
    }
