import json
import math
import time
from datetime import timedelta
from typing import Generator, TypedDict
from uuid import UUID

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.chatbot.models.models import ChatbotSession

SESSION_EXPIRE_MINUTES = 30
SESSION_TTL_SECONDS = SESSION_EXPIRE_MINUTES * 60
STREAM_LOCK_TTL = 60

OUT_OF_SCOPE_ANSWER = "올바른 질문이 아닙니다."


class SiteKnowledge(TypedDict):
    keywords: tuple[str, ...]
    answer: str


SITE_SCOPE_KEYWORDS = (
    "게임",
    "설문",
    "추천",
    "취향",
    "장르",
    "스타일",
    "좋아요",
    "찜",
    "북마크",
    "별점",
    "평점",
    "인기",
    "top100",
    "top 100",
    "탑100",
    "탑 100",
    "아이디",
    "비밀번호",
    "회원가입",
    "로그인",
    "로그아웃",
    "계정",
    "프로필",
    "회원",
    "가입",
    "비번",
    "패스워드",
    "password",
)

SITE_KNOWLEDGE_BASE: list[SiteKnowledge] = [
    {
        "keywords": ("사이트",),
        "answer": "우리 사이트는 게임 설문조사를 통해 사용자의 장르와 스타일 취향을 파악하고, 취향에 맞는 게임을 추천해 주는 서비스입니다.",
    },
    {
        "keywords": ("아이디", "찾"),
        "answer": "아이디 찾기는 가입한 계정 정보를 확인하는 기능입니다. 화면에서 요구하는 본인 확인 절차를 진행해 주세요.",
    },
    {
        "keywords": ("비밀번호",),
        "answer": "비밀번호를 잊은 경우 비밀번호 찾기 또는 재설정 기능을 통해 새 비밀번호로 변경할 수 있습니다.",
    },
    {
        "keywords": ("비번",),
        "answer": "비밀번호를 잊은 경우 비밀번호 찾기 또는 재설정 기능을 통해 새 비밀번호로 변경할 수 있습니다.",
    },
    {
        "keywords": ("패스워드",),
        "answer": "패스워드를 잊은 경우 비밀번호 찾기 또는 재설정 기능을 통해 새 비밀번호로 변경할 수 있습니다.",
    },
    {
        "keywords": ("회원가입",),
        "answer": "회원가입은 아이디, 비밀번호, 이름, 닉네임, 성별 등 필수 정보를 입력해 진행할 수 있습니다.",
    },
    {
        "keywords": ("회원", "가입"),
        "answer": "회원가입은 아이디, 비밀번호, 이름, 닉네임, 성별 등 필수 정보를 입력해 진행할 수 있습니다.",
    },
    {
        "keywords": ("로그인",),
        "answer": "로그인은 가입한 아이디와 비밀번호로 진행합니다. 로그인 후에는 토큰을 통해 인증 상태가 유지됩니다.",
    },
    {
        "keywords": ("로그아웃",),
        "answer": "로그아웃하면 현재 로그인 토큰이 종료되어 다시 로그인해야 합니다.",
    },
    {
        "keywords": ("게임", "추천"),
        "answer": "게임 추천은 설문조사 답변과 사용자의 장르, 스타일 취향을 바탕으로 어울리는 게임을 안내하는 기능입니다.",
    },
    {
        "keywords": ("맞춤", "추천"),
        "answer": "맞춤 추천은 설문조사에서 확인한 취향 정보를 바탕으로 사용자가 좋아할 만한 게임을 보여줍니다.",
    },
    {
        "keywords": ("설문",),
        "answer": "게임 설문조사에서 장르와 플레이 스타일에 대한 질문에 답하면, 그 결과를 바탕으로 관련 게임을 추천받을 수 있습니다.",
    },
    {
        "keywords": ("취향",),
        "answer": "취향 분석은 설문 답변을 기반으로 좋아하는 장르와 스타일을 파악하고 게임 추천에 활용합니다.",
    },
    {
        "keywords": ("장르",),
        "answer": "좋아하는 장르는 설문조사와 취향 정보를 바탕으로 추천 결과에 반영됩니다.",
    },
    {
        "keywords": ("스타일",),
        "answer": "선호하는 플레이 스타일은 설문조사 답변을 통해 파악하며, 취향에 맞는 게임 추천에 사용됩니다.",
    },
    {
        "keywords": ("북마크",),
        "answer": "마음에 드는 게임은 좋아요를 눌러 찜한 게임처럼 저장할 수 있습니다.",
    },
    {
        "keywords": ("찜",),
        "answer": "추천받은 게임이나 마음에 드는 게임은 좋아요를 눌러 찜 목록처럼 관리할 수 있습니다.",
    },
    {
        "keywords": ("좋아요",),
        "answer": "게임 좋아요는 마음에 드는 게임을 찜하는 기능이며, 관심 있는 게임을 저장하는 데 사용할 수 있습니다.",
    },
    {
        "keywords": ("별점",),
        "answer": "별점은 게임에 대한 사용자 평가로 활용되며, 인기 TOP100 게임을 보여주는 기준에 반영됩니다.",
    },
    {
        "keywords": ("평점",),
        "answer": "평점은 별점 평가를 통해 계산되며, 인기 게임을 정렬하고 보여주는 데 활용됩니다.",
    },
    {
        "keywords": ("인기",),
        "answer": "인기 TOP100은 사용자 별점과 평가 정보를 바탕으로 인기 있는 게임 100개를 보여주는 기능입니다.",
    },
    {
        "keywords": ("top100",),
        "answer": "인기 TOP100에서는 별점 기반으로 많은 관심을 받은 게임들을 확인할 수 있습니다.",
    },
    {
        "keywords": ("top 100",),
        "answer": "인기 TOP100에서는 별점 기반으로 많은 관심을 받은 게임들을 확인할 수 있습니다.",
    },
    {
        "keywords": ("탑100",),
        "answer": "인기 TOP100에서는 별점 기반으로 많은 관심을 받은 게임들을 확인할 수 있습니다.",
    },
    {
        "keywords": ("탑 100",),
        "answer": "인기 TOP100에서는 별점 기반으로 많은 관심을 받은 게임들을 확인할 수 있습니다.",
    },
    {
        "keywords": ("게임", "안나와요"),
        "answer": "게임이 검색되지 않는 경우 정확한 게임명 또는 유사한 검색어로 다시 시도해 주세요.",
    },
    {
        "keywords": ("계정 삭제",),
        "answer": "계정 삭제는 마이페이지의 회원 탈퇴 메뉴에서 진행할 수 있습니다.",
    },
]


def _normalize_session_id(session_id: UUID | str) -> str:
    return str(session_id)


def _stream_lock_key(session_id: UUID | str) -> str:
    normalized_session_id = _normalize_session_id(session_id)
    return f"chatbot:streaming:{normalized_session_id}"


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

    # 🔥 추가 (핵심)
    session.expires_at = timezone.now() + timedelta(seconds=SESSION_TTL_SECONDS)
    session.save(update_fields=["expires_at"])

    return session


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


def acquire_stream_lock(session_id: UUID | str) -> bool:
    return cache.add(_stream_lock_key(session_id), True, timeout=STREAM_LOCK_TTL)


def release_stream_lock(session_id: UUID | str) -> None:
    cache.delete(_stream_lock_key(session_id))


def is_streaming(session_id: UUID | str) -> bool:
    return cache.get(_stream_lock_key(session_id)) is not None


def build_answer(message: str) -> str:
    normalized = message.strip()
    lowered = normalized.lower()

    if not any(keyword in lowered for keyword in SITE_SCOPE_KEYWORDS):
        return OUT_OF_SCOPE_ANSWER

    for knowledge in SITE_KNOWLEDGE_BASE:
        if all(keyword in lowered for keyword in knowledge["keywords"]):
            return knowledge["answer"]

    return (
        "우리 사이트는 게임 설문조사로 취향을 파악해 게임을 추천하고, 좋아요/찜과 별점으로 "
        "관심 게임과 인기 TOP100을 확인할 수 있는 서비스입니다. 설문, 추천, 취향, 좋아요, 별점, "
        "인기 TOP100 중 궁금한 내용을 조금 더 구체적으로 입력해 주세요."
    )


def chunk_text(text: str, size: int = 6) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def generate_stream(
    session: ChatbotSession, question: str
) -> Generator[str, None, None]:
    answer = build_answer(question)
    session_payload = build_session_payload(session)

    yield format_sse("start", session_payload)

    for chunk in chunk_text(answer):
        yield format_sse("chunk", {"content": chunk})
        time.sleep(0.05)

    yield format_sse("complete", session_payload)
