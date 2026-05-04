from uuid import UUID

from apps.chatbot.models.models import ChatbotSession


def save_question_to_cache(session_id: UUID | str, message: str) -> None:
    ChatbotSession.objects.filter(pk=session_id).update(pending_question=message)


def get_question_from_cache(session_id: UUID | str) -> str | None:
    session = (
        ChatbotSession.objects.filter(pk=session_id).only("pending_question").first()
    )
    if session is None:
        return None
    return session.pending_question


def delete_question_from_cache(session_id: UUID | str) -> None:
    ChatbotSession.objects.filter(pk=session_id).update(pending_question=None)
