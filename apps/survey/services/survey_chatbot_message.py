import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

import requests
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from apps.survey.choices import SurveyRoleChoices, SurveyStatusChoices
from apps.survey.models import (
    SurveyChatbotMessage,
    SurveyChatbotSession,
    SurveyResults,
)
from apps.survey.prompts.survey_chatbot_message_intent_prompt import (
    SURVEY_CHATBOT_MESSAGE_INTENT_PROMPT,
    SURVEY_CHATBOT_MESSAGE_INTENT_SYSTEM_PROMPT,
    SURVEY_CHATBOT_MESSAGE_INTENT_USER_PROMPT,
)
from apps.survey.prompts.survey_chatbot_question_generation_prompt import (
    SURVEY_CHATBOT_QUESTION_GENERATION_PROMPT,
    SURVEY_CHATBOT_QUESTION_GENERATION_SYSTEM_PROMPT,
    SURVEY_CHATBOT_QUESTION_GENERATION_USER_PROMPT,
)
from apps.survey.prompts.survey_chatbot_summary_prompt import (
    SURVEY_CHATBOT_SUMMARY_PROMPT,
    SURVEY_CHATBOT_SUMMARY_SYSTEM_PROMPT,
    SURVEY_CHATBOT_SUMMARY_USER_PROMPT,
)
from apps.survey.services.survey_chatbot_session import (
    SURVEY_COMPLETION_MESSAGE,
    SurveyChatbotSessionService,
    SurveyQuestionGenerationUnavailable,
)
from apps.users.models import UserPreference

UNRELATED_COUNT_TTL = 60 * 30
UNRELATED_LOCK_SECONDS = 60 * 5
UNRELATED_MAX_ATTEMPTS = 3
PROFANITY_WARNING_MESSAGE = "비속어가 포함되어있습니다. 답변을 다시 작성해 주세요."
OBVIOUS_UNRELATED_PATTERNS = (
    r"프롬프트",
    r"system prompt",
    r"시스템 프롬프트",
    r"이제부터",
    r"ignore",
    r"developer message",
    r"무슨\s*게임.*재밌",
    r"게임\s*추천",
)
PROFANITY_PATTERNS = (
    r"존나",
    r"ㅈㄴ",
    r"시발",
    r"씨발",
    r"ㅅㅂ",
    r"병신",
    r"개새",
    r"좆",
    r"꺼져",
)
GAME_PREFERENCE_SIGNAL_PATTERNS = (
    r"좋",
    r"싫",
    r"재밌",
    r"몰입",
    r"쾌감",
    r"성취감",
    r"선호",
    r"피곤",
    r"압박감",
    r"어렵",
    r"쉬운",
    r"전투",
    r"성장",
    r"탐험",
    r"스토리",
    r"협동",
    r"경쟁",
    r"보스",
    r"장르",
    r"액션",
    r"RPG",
    r"FPS",
    r"퍼즐",
    r"전략",
    r"시뮬",
    r"레이싱",
    r"스포츠",
    r"분위기",
    r"세계관",
    r"캐릭터",
    r"스킬",
    r"에이스",
    r"공략",
    r"플레이",
)
UNCERTAIN_PREFERENCE_PATTERNS = (
    r"상황\s*따라",
    r"케바케",
    r"둘\s*다",
    r"반반",
    r"아무거나",
    r"딱히",
    r"애매",
)
ACTIVE_GENRE_CONTEXT_KEYWORDS = {
    "액션": ("액션", "손맛", "회피", "공격 타이밍"),
    "어드벤처": ("어드벤처", "탐험", "발견", "세계"),
    "RPG": ("rpg", "성장", "레벨", "장비", "파밍", "빌드", "보스"),
    "슈팅": ("슈팅", "fps", "에임", "포지셔닝", "교전", "사이트", "스파이크"),
    "전략": ("전략", "운영", "자원", "빌드오더", "전술"),
    "시뮬레이션": ("시뮬레이션", "운영 효율", "관리", "루틴"),
    "스포츠": ("스포츠", "경기", "선수", "팀 운영"),
    "레이싱": ("레이싱", "기록", "코스", "속도감"),
    "퍼즐": ("퍼즐", "문제", "규칙", "논리"),
    "플랫폼": ("플랫폼", "점프", "타이밍", "조작"),
    "대전격투": ("격투", "콤보", "심리전", "반격", "카운터"),
    "카드/보드": ("카드", "보드", "덱", "수읽기"),
    "음악/리듬": ("리듬", "음악", "정확도", "박자"),
    "비주얼노벨": ("비주얼노벨", "감정선", "캐릭터 관계"),
}
FALLBACK_REASK_PATTERNS = (
    r"잘\s*모르겠",
    r"모르겠어",
    r"모르겠어요",
    r"모르겠습니다",
    r"모르겠네",
    r"모르겠는데",
    r"모르겠음",
    r"기억이\s*안\s*나",
    r"기억이\s*잘\s*안\s*나",
    r"기억이\s*잘\s*안\s*나요",
    r"딱히\s*없",
    r"잘\s*생각이\s*안\s*나",
    r"잘\s*생각이\s*안\s*나요",
    r"애매",
    r"질문이\s*어렵",
    r"답하기\s*어렵",
    r"뭐라고\s*답",
    r"어떻게\s*답",
    r"다른\s*질문",
)
FALLBACK_CLARIFY_PATTERNS = (
    r"무슨\s*뜻",
    r"무슨\s*말",
    r"이해가\s*안",
    r"다시\s*설명",
    r"쉽게\s*설명",
    r"그게\s*무슨",
    r"이게\s*무슨",
    r"질문\s*뜻",
)
SUMMARY_SIMILARITY_STOPWORDS = {
    "사용자는",
    "게임",
    "재미",
    "느낍니다",
    "좋아하며",
    "선호하는",
    "선호합니다",
    "경향이",
    "있습니다",
    "특히",
    "과정에서",
    "경험을",
    "플레이",
}
SUMMARY_GENERATION_MAX_ATTEMPTS = 3
FALLBACK_SUMMARY_MAX_LENGTH = 500
COMPLETE_SUMMARY_ENDINGS = (
    "합니다.",
    "습니다.",
    "됩니다.",
    "있습니다.",
    "느낍니다.",
    "선호합니다.",
    "좋아합니다.",
    "즐깁니다.",
    ".",
    "!",
    "?",
)
INCOMPLETE_SUMMARY_ENDINGS = (
    "을",
    "를",
    "이",
    "가",
    "은",
    "는",
    "와",
    "과",
    "로",
    "으로",
    "의",
    "에",
    "에서",
    "에게",
    "하며",
    "하고",
    "하는",
    "선호",
    "좋아",
    "느끼",
    "즐기",
    "중요",
)
DIRECT_GAME_KEYWORD_PATTERNS = (
    r"(?P<keyword>[가-힣A-Za-z0-9][가-힣A-Za-z0-9 .:'’+\-]{1,40}?)(?:이랑|랑|하고|와|과)\s",
    r"(?P<keyword>[가-힣A-Za-z0-9][가-힣A-Za-z0-9 .:'’+\-]{1,40}?)(?:을|를|은|는|이|가)\s*(?:좋|재밌|즐겨|선호|해봤|했)",
    r"(?P<keyword>[가-힣A-Za-z0-9][가-힣A-Za-z0-9 .:'’+\-]{1,40}?)(?:에서|으로)\s",
)
DIRECT_GAME_SUFFIX_PATTERN = (
    r"(?P<keyword>[가-힣A-Za-z0-9][가-힣A-Za-z0-9 .:'’+\-]{1,40}?)(?:처럼|같은|같이)"
)
DIRECT_GAME_CONTEXT_PATTERNS = (
    r"(?P<keyword>[가-힣A-Za-z0-9][가-힣A-Za-z0-9 .:'’+\-]{1,40}?)(?:\s*할\s*때|\s*할때|\s*하면서|\s*하면)",
)
DIRECT_GAME_CONNECTORS = r"(?:이랑|랑|하고|와|과|,|/)"
DIRECT_GAME_KEYWORD_STOPWORDS = {
    "게임",
    "장르",
    "분위기",
    "전투",
    "탐험",
    "성장",
    "보스",
    "보스 몬스터",
    "스토리",
    "캐릭터",
    "스킬",
    "사이트",
    "영역",
    "플레이",
}


class SurveyChatbotSessionClosed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "이미 종료된 설문 세션입니다."
    default_code = "survey_chatbot_session_closed"


class SurveyChatbotSessionLocked(APIException):
    status_code = status.HTTP_423_LOCKED
    default_detail = "질문과 무관한 답변이 반복되어 5분간 설문이 비활성화되었습니다."
    default_code = "survey_chatbot_session_locked"

    def __init__(self, retry_after_seconds: int):
        super().__init__(self.default_detail)
        self.retry_after_seconds = retry_after_seconds


class SurveySummaryGenerationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "설문 결과를 정리하지 못했습니다. 잠시 후 다시 시도해주세요."
    default_code = "survey_summary_generation_unavailable"


class SurveyEmbeddingGenerationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "설문 추천 준비에 필요한 벡터 저장에 실패했습니다. 잠시 후 다시 시도해주세요."
    )
    default_code = "survey_embedding_generation_unavailable"


@dataclass(frozen=True)
class SurveyChatbotMessageResult:
    session_id: str
    status: str
    ai_message: str | None
    progress: dict
    recommendation_ready: bool
    survey_answer: str | None = None
    excluded_keywords: list[str] | None = None
    warning_message: str | None = None

    def as_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "warning_message": self.warning_message,
            "ai_message": self.ai_message,
            "progress": self.progress,
            "recommendation_ready": self.recommendation_ready,
            "survey_answer": self.survey_answer,
            "excluded_keywords": self.excluded_keywords or [],
        }


class SurveyChatbotMessageService:
    def __init__(self) -> None:
        self.session_service = SurveyChatbotSessionService()

    def handle_message(
        self, user: Any, session_id: UUID | str, message: str
    ) -> SurveyChatbotMessageResult:
        session = self.get_user_session(user=user, session_id=session_id)

        if session.status == SurveyStatusChoices.CLOSED:
            raise SurveyChatbotSessionClosed()

        retry_after_seconds = self.get_lock_retry_after_seconds(session.id)
        if retry_after_seconds > 0:
            raise SurveyChatbotSessionLocked(retry_after_seconds)

        if self.contains_profanity(message):
            return self.handle_unrelated_answer(
                session=session,
                warning_message=PROFANITY_WARNING_MESSAGE,
            )

        current_question = self.get_current_question(session)
        intent = self.classify_user_message_intent(
            current_question=current_question,
            user_message=message,
            session=session,
        )
        if intent == "UNRELATED":
            return self.handle_unrelated_answer(session=session)

        if intent == "CLARIFY":
            return self.handle_clarify_answer(
                session=session,
                current_question=current_question,
                user_message=message,
            )

        if intent == "REASK":
            return self.handle_reask_answer(
                session=session,
                current_question=current_question,
                user_message=message,
            )

        with transaction.atomic():
            self.save_user_message(session=session, message=message)

            if session.target_question_count is None:
                session.target_question_count = self.decide_target_question_count(
                    message
                )

            current_step = session.messages.filter(role=SurveyRoleChoices.USER).count()

            if current_step >= session.target_question_count:
                survey_answer, excluded_keywords = self.summarize_session(session)
                recommendation_ready = True
                warning_message = None
                survey_vector = None
                try:
                    survey_vector = self.generate_survey_embedding(survey_answer)
                except SurveyEmbeddingGenerationUnavailable:
                    recommendation_ready = False
                    warning_message = "설문은 종료되었지만 추천 준비가 지연되고 있습니다. 잠시 후 다시 확인해 주세요."
                SurveyResults.objects.update_or_create(
                    chatbot_session=session,
                    defaults={
                        "user": user,
                        "survey_answer": survey_answer,
                        "excluded_keywords": json.dumps(
                            excluded_keywords, ensure_ascii=False
                        ),
                    },
                )
                UserPreference.objects.update_or_create(
                    user=user,
                    defaults={
                        "survey_vector": survey_vector,
                    },
                )
                session.status = SurveyStatusChoices.CLOSED
                session.save(update_fields=["target_question_count", "status"])

                return SurveyChatbotMessageResult(
                    session_id=str(session.id),
                    status=session.status,
                    ai_message=SURVEY_COMPLETION_MESSAGE,
                    progress=self.session_service.build_progress(session),
                    recommendation_ready=recommendation_ready,
                    survey_answer=survey_answer,
                    excluded_keywords=excluded_keywords,
                    warning_message=warning_message,
                )

            next_question = self.generate_next_question(session=session)
            self.save_ai_message(session=session, message=next_question)
            session.status = SurveyStatusChoices.IN_PROGRESS
            session.save(update_fields=["target_question_count", "status"])

        return SurveyChatbotMessageResult(
            session_id=str(session.id),
            status=session.status,
            ai_message=next_question,
            progress=self.session_service.build_progress(session),
            recommendation_ready=False,
        )

    def get_user_session(
        self, user: Any, session_id: UUID | str
    ) -> SurveyChatbotSession:
        try:
            return SurveyChatbotSession.objects.prefetch_related("messages").get(
                id=session_id,
                user=user,
            )
        except SurveyChatbotSession.DoesNotExist as exc:
            raise NotFound("설문 챗봇 세션을 찾을 수 없습니다.") from exc

    def get_current_question(self, session: SurveyChatbotSession) -> str:
        question = self.session_service.get_current_question(session)
        if not question:
            raise SurveyQuestionGenerationUnavailable()
        return question

    def handle_unrelated_answer(
        self,
        session: SurveyChatbotSession,
        warning_message: str = "설문 질문과 관련된 게임 취향 답변을 입력해주세요.",
    ) -> SurveyChatbotMessageResult:
        attempts = self.increment_unrelated_attempts(session.id)
        if attempts >= UNRELATED_MAX_ATTEMPTS:
            self.set_lock(session.id)
            self.reset_unrelated_attempts(session.id)
            raise SurveyChatbotSessionLocked(UNRELATED_LOCK_SECONDS)

        return SurveyChatbotMessageResult(
            session_id=str(session.id),
            status=session.status,
            warning_message=warning_message,
            ai_message=self.get_current_question(session),
            progress=self.session_service.build_progress(session),
            recommendation_ready=False,
        )

    def handle_reask_answer(
        self,
        session: SurveyChatbotSession,
        current_question: str,
        user_message: str,
    ) -> SurveyChatbotMessageResult:
        next_question = self.generate_rephrased_question(
            session=session,
            current_question=current_question,
            user_message=user_message,
        )
        with transaction.atomic():
            self.save_ai_message(session=session, message=next_question)

        return SurveyChatbotMessageResult(
            session_id=str(session.id),
            status=session.status,
            warning_message="다른 질문으로 바꿔서 여쭤보겠습니다.",
            ai_message=next_question,
            progress=self.session_service.build_progress(session),
            recommendation_ready=False,
        )

    def handle_clarify_answer(
        self,
        session: SurveyChatbotSession,
        current_question: str,
        user_message: str,
    ) -> SurveyChatbotMessageResult:
        next_question = self.generate_clarified_question(
            session=session,
            current_question=current_question,
            user_message=user_message,
        )
        with transaction.atomic():
            self.save_ai_message(session=session, message=next_question)

        return SurveyChatbotMessageResult(
            session_id=str(session.id),
            status=session.status,
            warning_message="같은 의미를 더 쉽게 다시 물어볼게요!",
            ai_message=next_question,
            progress=self.session_service.build_progress(session),
            recommendation_ready=False,
        )

    def save_user_message(self, session: SurveyChatbotSession, message: str) -> None:
        SurveyChatbotMessage.objects.create(
            session=session,
            message=message,
            role=SurveyRoleChoices.USER,
            sequence=self.get_next_sequence(session),
        )

    def save_ai_message(self, session: SurveyChatbotSession, message: str) -> None:
        SurveyChatbotMessage.objects.create(
            session=session,
            message=message,
            role=SurveyRoleChoices.AI,
            sequence=self.get_next_sequence(session),
        )

    def get_next_sequence(self, session: SurveyChatbotSession) -> int:
        last_message = session.messages.order_by("-sequence").first()
        return (last_message.sequence or 0) + 1 if last_message else 1

    def is_related_answer(self, current_question: str, user_message: str) -> bool:
        return (
            self.classify_user_message_intent(
                current_question=current_question,
                user_message=user_message,
            )
            != "UNRELATED"
        )

    def is_obviously_unrelated(self, normalized_message: str) -> bool:
        return any(
            re.search(pattern, normalized_message, flags=re.IGNORECASE)
            for pattern in OBVIOUS_UNRELATED_PATTERNS
        )

    def contains_profanity(self, message: str) -> bool:
        return any(
            re.search(pattern, message, flags=re.IGNORECASE)
            for pattern in PROFANITY_PATTERNS
        )

    def has_game_preference_signal(self, normalized_message: str) -> bool:
        return any(
            re.search(pattern, normalized_message, flags=re.IGNORECASE)
            for pattern in GAME_PREFERENCE_SIGNAL_PATTERNS
        )

    def is_uncertain_preference_answer(self, normalized_message: str) -> bool:
        return any(
            re.search(pattern, normalized_message, flags=re.IGNORECASE)
            for pattern in (*FALLBACK_REASK_PATTERNS, *UNCERTAIN_PREFERENCE_PATTERNS)
        )

    def should_reask_question(self, current_question: str, user_message: str) -> bool:
        return (
            self.classify_user_message_intent(
                current_question=current_question,
                user_message=user_message,
            )
            == "REASK"
        )

    def is_fallback_reask_answer(self, normalized_message: str) -> bool:
        return any(
            re.search(pattern, normalized_message, flags=re.IGNORECASE)
            for pattern in FALLBACK_REASK_PATTERNS
        )

    def is_fallback_clarify_answer(self, normalized_message: str) -> bool:
        return any(
            re.search(pattern, normalized_message, flags=re.IGNORECASE)
            for pattern in FALLBACK_CLARIFY_PATTERNS
        )

    def build_message_intent_prompt(
        self,
        current_question: str,
        user_message: str,
        session: SurveyChatbotSession | None = None,
    ) -> str:
        nickname = self.session_service.get_user_nickname(
            session.user if session else None
        )
        return (
            f"{SURVEY_CHATBOT_MESSAGE_INTENT_PROMPT.strip().format(nickname=nickname)}\n\n"
            f"현재 질문:\n{current_question}\n\n"
            f"{nickname}님 답변:\n{user_message}\n"
        )

    def build_message_intent_prompts(
        self,
        current_question: str,
        user_message: str,
        session: SurveyChatbotSession | None = None,
    ) -> tuple[str, str]:
        nickname = self.session_service.get_user_nickname(
            session.user if session else None
        )
        system_prompt = SURVEY_CHATBOT_MESSAGE_INTENT_SYSTEM_PROMPT.strip().format(
            nickname=nickname
        )
        user_prompt = (
            f"{SURVEY_CHATBOT_MESSAGE_INTENT_USER_PROMPT.strip().format(nickname=nickname)}\n\n"
            f"## 현재 질문\n\n{current_question}\n\n"
            f"## {nickname}님 답변\n\n{user_message}\n"
        )
        return system_prompt, user_prompt

    def classify_user_message_intent(
        self,
        current_question: str,
        user_message: str,
        session: SurveyChatbotSession | None = None,
    ) -> str:
        normalized_message = user_message.strip().lower()
        if self.is_obviously_unrelated(normalized_message):
            return "UNRELATED"
        if self.is_fallback_clarify_answer(normalized_message):
            return "CLARIFY"
        if self.has_game_preference_signal(normalized_message):
            return "NORMAL"
        if self.is_fallback_reask_answer(normalized_message):
            return "REASK"

        system_prompt, user_prompt = self.build_message_intent_prompts(
            current_question=current_question,
            user_message=user_message,
            session=session,
        )
        response = self.session_service.generate_question_with_llm(
            user_prompt,
            temperature=0.1,
            system_prompt=system_prompt,
        )
        if response:
            normalized_response = response.strip().upper()
            if normalized_response.startswith("UNRELATED"):
                return "UNRELATED"
            if normalized_response.startswith("CLARIFY"):
                return "CLARIFY"
            if normalized_response.startswith("REASK"):
                return "REASK"
            if normalized_response.startswith("NORMAL"):
                return "NORMAL"

        return "NORMAL"

    def decide_target_question_count(self, user_message: str) -> int:
        return self.fallback_target_question_count(user_message)

    def fallback_target_question_count(self, user_message: str) -> int:
        normalized = user_message.strip()
        if len(normalized) >= 80 or normalized.count(" ") >= 12:
            return 3
        if len(normalized) >= 40 or normalized.count(" ") >= 6:
            return 4
        return 5

    def generate_next_question(self, session: SurveyChatbotSession) -> str:
        system_prompt, prompt = self.build_next_question_prompts(session)
        latest_user_message = self.get_latest_user_message(session)
        question = self.session_service.generate_valid_question(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.4,
            log_message="Invalid follow-up survey question generated by LLM: %s",
            mode="NEXT",
            previous_questions=self.get_previous_ai_questions(session),
            latest_user_message=latest_user_message,
            nickname=self.session_service.get_user_nickname(session.user),
        )
        if question:
            return question
        raise SurveyQuestionGenerationUnavailable()

    # 이 기능은 직전 유저 답변을 중심으로 후속 질문 프롬프트를 구성
    def build_next_question_prompt(self, session: SurveyChatbotSession) -> str:
        return self.build_question_generation_prompt(
            mode="NEXT",
            session=session,
            current_question=self.get_current_question(session),
            user_message="",
        )

    def build_next_question_prompts(
        self, session: SurveyChatbotSession
    ) -> tuple[str, str]:
        return self.build_question_generation_prompts(
            mode="NEXT",
            session=session,
            current_question=self.get_current_question(session),
            user_message="",
        )

    def build_question_generation_prompt(
        self,
        mode: str,
        session: SurveyChatbotSession,
        current_question: str,
        user_message: str,
    ) -> str:
        _, user_prompt = self.build_question_generation_prompts(
            mode=mode,
            session=session,
            current_question=current_question,
            user_message=user_message,
        )
        return user_prompt

    # 이 기능은 질문 생성 프롬프트를 시스템/유저 프롬프트로 나눠 상황별로 재사용
    def build_question_generation_prompts(
        self,
        mode: str,
        session: SurveyChatbotSession,
        current_question: str,
        user_message: str,
    ) -> tuple[str, str]:
        conversation = self.build_conversation_text(session)
        latest_user_message = self.get_latest_user_message(session)
        confirmed_preferences, uncertain_preferences = self.build_preference_state(
            session
        )
        active_genre_context = self.detect_active_genre_context(session)
        anchor_answer = self.get_anchor_answer(session)
        anchor_topics = self.build_anchor_topics(anchor_answer)
        values = {
            "nickname": self.session_service.get_user_nickname(session.user),
            "mode": mode,
            "current_step": session.messages.filter(
                role=SurveyRoleChoices.USER
            ).count(),
            "target_question_count": session.target_question_count,
            "anchor_answer": anchor_answer,
            "anchor_topics": anchor_topics,
            "confirmed_preferences": confirmed_preferences,
            "uncertain_preferences": uncertain_preferences,
            "active_genre_context": active_genre_context,
            "current_question": current_question,
            "latest_user_message": latest_user_message,
            "conversation": conversation,
        }
        return (
            SURVEY_CHATBOT_QUESTION_GENERATION_SYSTEM_PROMPT.strip().format(**values),
            SURVEY_CHATBOT_QUESTION_GENERATION_USER_PROMPT.strip().format(**values),
        )

    def get_anchor_answer(self, session: SurveyChatbotSession) -> str:
        return (
            session.messages.filter(role=SurveyRoleChoices.USER)
            .order_by("sequence")
            .values_list("message", flat=True)
            .first()
            or "없음"
        )

    def build_anchor_topics(self, anchor_answer: str) -> str:
        if not anchor_answer or anchor_answer == "없음":
            return "없음"

        topic_labels = {
            "genre": "선호 장르",
            "difficulty": "난이도 성향",
            "coop_competition": "경쟁/협동 성향",
            "story": "스토리 몰입",
            "combat": "전투 스타일",
            "exploration": "탐험 성향",
            "growth": "성장 방식",
            "tempo": "플레이 템포",
            "reward": "보상 구조",
            "mastery": "숙련/캐릭터 운용",
        }
        topics = self.session_service.detect_question_topics(anchor_answer)
        labels = [label for key, label in topic_labels.items() if key in topics]
        return ", ".join(labels) if labels else "없음"

    def get_latest_user_message(self, session: SurveyChatbotSession) -> str:
        return (
            session.messages.filter(role=SurveyRoleChoices.USER)
            .order_by("-sequence")
            .values_list("message", flat=True)
            .first()
            or ""
        )

    def get_previous_ai_questions(self, session: SurveyChatbotSession) -> list[str]:
        return list(
            session.messages.filter(role=SurveyRoleChoices.AI)
            .order_by("sequence")
            .values_list("message", flat=True)
        )

    def build_preference_state(self, session: SurveyChatbotSession) -> tuple[str, str]:
        topic_labels = {
            "genre": "선호 장르",
            "difficulty": "난이도 성향",
            "coop_competition": "경쟁/협동 성향",
            "story": "스토리 몰입",
            "combat": "전투 스타일",
            "exploration": "탐험 성향",
            "growth": "성장 방식",
            "tempo": "플레이 템포",
            "reward": "보상 구조",
            "mastery": "숙련/캐릭터 운용",
        }
        confirmed_keys = set()
        uncertain_keys = set()
        for message in session.messages.filter(role=SurveyRoleChoices.USER).values_list(
            "message", flat=True
        ):
            message_topics = self.session_service.detect_question_topics(message)
            if self.is_uncertain_preference_answer(message.strip().lower()):
                uncertain_keys.update(message_topics)
                continue
            confirmed_keys.update(message_topics)

        asked_text = "\n".join(self.get_previous_ai_questions(session))
        asked_keys = self.session_service.detect_question_topics(asked_text)
        uncertain_keys.update(asked_keys - confirmed_keys)
        uncertain_keys.update(set(topic_labels) - confirmed_keys - uncertain_keys)

        confirmed_preferences = [
            label for key, label in topic_labels.items() if key in confirmed_keys
        ]
        uncertain_preferences = [
            label for key, label in topic_labels.items() if key in uncertain_keys
        ]
        return (
            ", ".join(confirmed_preferences) if confirmed_preferences else "없음",
            ", ".join(uncertain_preferences) if uncertain_preferences else "없음",
        )

    def detect_active_genre_context(self, session: SurveyChatbotSession) -> str:
        messages = list(
            session.messages.order_by("-sequence").values_list("message", flat=True)[:4]
        )
        recent_text = " ".join(reversed(messages)).lower()
        if not recent_text.strip():
            return "없음"

        matched_contexts = []
        for genre_name, keywords in ACTIVE_GENRE_CONTEXT_KEYWORDS.items():
            if any(keyword.lower() in recent_text for keyword in keywords):
                matched_contexts.append(genre_name)

        return ", ".join(matched_contexts) if matched_contexts else "없음"

    def generate_rephrased_question(
        self,
        session: SurveyChatbotSession,
        current_question: str,
        user_message: str,
    ) -> str:
        system_prompt, prompt = self.build_question_generation_prompts(
            mode="REASK",
            session=session,
            current_question=current_question,
            user_message=user_message,
        )
        question = self.session_service.generate_valid_question(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.4,
            log_message="Invalid rephrased survey question generated by LLM: %s",
            mode="REASK",
            previous_questions=self.get_previous_ai_questions(session),
            latest_user_message=user_message,
            nickname=self.session_service.get_user_nickname(session.user),
        )
        if question:
            return question
        return current_question

    def generate_clarified_question(
        self,
        session: SurveyChatbotSession,
        current_question: str,
        user_message: str,
    ) -> str:
        system_prompt, prompt = self.build_question_generation_prompts(
            mode="CLARIFY",
            session=session,
            current_question=current_question,
            user_message=user_message,
        )
        question = self.session_service.generate_valid_question(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.4,
            log_message="Invalid clarified survey question generated by LLM: %s",
            mode="CLARIFY",
            previous_questions=self.get_previous_ai_questions(session),
            latest_user_message=user_message,
            nickname=self.session_service.get_user_nickname(session.user),
        )
        if question:
            return question
        return current_question

    def summarize_session(self, session: SurveyChatbotSession) -> tuple[str, list[str]]:
        user_messages = list(
            session.messages.filter(role=SurveyRoleChoices.USER).values_list(
                "message", flat=True
            )
        )
        prompt_values = {
            "nickname": self.session_service.get_user_nickname(session.user),
            "user_messages": "\n".join(f"- {message}" for message in user_messages),
        }
        system_prompt = SURVEY_CHATBOT_SUMMARY_SYSTEM_PROMPT.strip().format(
            **prompt_values
        )
        prompt = SURVEY_CHATBOT_SUMMARY_USER_PROMPT.strip().format(**prompt_values)
        direct_keywords = self.extract_direct_game_keywords(user_messages)

        for _ in range(SUMMARY_GENERATION_MAX_ATTEMPTS):
            response = self.session_service.generate_question_with_llm(
                prompt,
                system_prompt=system_prompt,
            )
            if not response:
                continue

            survey_answer, _ = self.parse_summary_response(response)
            if self.is_complete_summary_answer(
                survey_answer
            ) and not self.has_repeated_summary_sentences(survey_answer):
                return survey_answer or "", direct_keywords

        fallback_summary = self.build_fallback_summary(user_messages)
        if fallback_summary:
            return fallback_summary, direct_keywords

        raise SurveySummaryGenerationUnavailable()

    def generate_survey_embedding(self, survey_answer: str) -> list[float]:
        api_key = settings.SURVEY_CHATBOT_GEMINI_API_KEY
        if not api_key:
            raise SurveyEmbeddingGenerationUnavailable()

        url = (
            f"{settings.SURVEY_CHATBOT_GEMINI_BASE_URL}/v1beta/models/"
            f"{settings.SURVEY_EMBEDDING_MODEL}:embedContent"
        )
        payload = {
            "model": f"models/{settings.SURVEY_EMBEDDING_MODEL}",
            "content": {
                "parts": [
                    {
                        "text": survey_answer,
                    }
                ]
            },
            "taskType": "RETRIEVAL_QUERY",
            "outputDimensionality": 1536,
        }

        try:
            response = requests.post(
                url=url,
                params={"key": api_key},
                json=payload,
                timeout=settings.SURVEY_EMBEDDING_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logging.getLogger(__name__).exception(
                "Failed to generate survey embedding."
            )
            raise SurveyEmbeddingGenerationUnavailable() from exc

        try:
            values = response.json()["embedding"]["values"]
        except (KeyError, TypeError) as exc:
            logging.getLogger(__name__).warning(
                "Invalid Gemini embedding response: %s",
                response.text,
            )
            raise SurveyEmbeddingGenerationUnavailable() from exc

        if not isinstance(values, list) or not values:
            raise SurveyEmbeddingGenerationUnavailable()

        return [float(value) for value in values]

    def parse_summary_response(self, response: str) -> tuple[str | None, list[str]]:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json\n", "", 1).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            extracted_answer = self.extract_survey_answer_from_broken_json(cleaned)
            if extracted_answer:
                return extracted_answer, []
            if '"survey_answer"' in cleaned:
                return None, []
            return cleaned or None, []

        return str(data.get("survey_answer") or "").strip() or None, []

    def extract_survey_answer_from_broken_json(self, response: str) -> str | None:
        match = re.search(
            r'"survey_answer"\s*:\s*"(?P<value>.*?)(?:"\s*,|\Z)',
            response,
            flags=re.DOTALL,
        )
        if not match:
            return None

        extracted = match.group("value").strip()
        extracted = extracted.rstrip('"').strip()
        if not extracted:
            return None

        return extracted.replace('\\"', '"').replace("\\n", " ").strip()

    def is_complete_summary_answer(self, survey_answer: str | None) -> bool:
        if not survey_answer:
            return False

        normalized = survey_answer.strip()
        if len(normalized) < 20:
            return False
        if normalized.endswith(INCOMPLETE_SUMMARY_ENDINGS):
            return False
        if not normalized.endswith(COMPLETE_SUMMARY_ENDINGS):
            return False
        return True

    def build_fallback_summary(self, user_messages: list[str]) -> str | None:
        cleaned_messages = [
            cleaned
            for message in user_messages
            if (cleaned := self.clean_summary_source_message(message))
        ]
        if not cleaned_messages:
            return None

        joined = " ".join(cleaned_messages)
        if len(joined) > FALLBACK_SUMMARY_MAX_LENGTH:
            joined = joined[:FALLBACK_SUMMARY_MAX_LENGTH].rstrip()

        return joined if joined.endswith(".") else f"{joined}."

    def clean_summary_source_message(self, message: str) -> str:
        cleaned = re.sub(r"\s+", " ", message).strip()
        return cleaned.rstrip(".!?。")

    def has_repeated_summary_sentences(self, survey_answer: str | None) -> bool:
        if not survey_answer:
            return False

        sentences = [
            sentence.strip()
            for sentence in re.split(r"[.!?。]\s*", survey_answer.strip())
            if sentence.strip()
        ]
        for index, sentence in enumerate(sentences):
            sentence_tokens = self.extract_summary_tokens(sentence)
            if not sentence_tokens:
                continue
            for next_sentence in sentences[index + 1 :]:
                next_tokens = self.extract_summary_tokens(next_sentence)
                if not next_tokens:
                    continue
                overlap_ratio = len(sentence_tokens & next_tokens) / min(
                    len(sentence_tokens), len(next_tokens)
                )
                if overlap_ratio >= 0.5:
                    return True
        return False

    def extract_summary_tokens(self, sentence: str) -> set[str]:
        tokens = re.findall(r"[가-힣A-Za-z0-9]+", sentence)
        return {
            normalized_token
            for token in tokens
            if (normalized_token := self.normalize_summary_token(token))
            and len(normalized_token) >= 2
            and normalized_token not in SUMMARY_SIMILARITY_STOPWORDS
        }

    def normalize_summary_token(self, token: str) -> str:
        normalized = re.sub(
            r"(으로|에서|에게|처럼|하고|하며|하는|하며|합니다|됩니다|입니다|"
            r"습니다|네요|어요|아요|는다|했다|했다|했다|했다|"
            r"은|는|이|가|을|를|의|도|로|과|와)$",
            "",
            token,
        )
        if normalized.endswith("공략"):
            return "공략"
        return normalized

    def normalize_excluded_keywords(self, keywords: list[Any]) -> list[str]:
        normalized_keywords = []
        seen_keywords = set()
        for keyword in keywords:
            normalized = self.clean_direct_game_keyword(str(keyword))
            if not normalized or normalized in seen_keywords:
                continue
            seen_keywords.add(normalized)
            normalized_keywords.append(normalized)
        return normalized_keywords

    def extract_direct_game_keywords(self, user_messages: list[str]) -> list[str]:
        suffix_keywords: list[str] = []
        db_checked_keywords: list[str] = []
        for message in user_messages:
            for pattern in DIRECT_GAME_CONTEXT_PATTERNS:
                for match in re.finditer(pattern, message, flags=re.IGNORECASE):
                    suffix_keywords.append(match.group("keyword"))

            for segment in re.split(DIRECT_GAME_CONNECTORS, message):
                for match in re.finditer(
                    DIRECT_GAME_SUFFIX_PATTERN,
                    segment,
                    flags=re.IGNORECASE,
                ):
                    suffix_keywords.append(match.group("keyword"))

            for pattern in DIRECT_GAME_KEYWORD_PATTERNS:
                for match in re.finditer(pattern, message, flags=re.IGNORECASE):
                    db_checked_keywords.append(match.group("keyword"))

        return self.normalize_excluded_keywords(
            [
                *suffix_keywords,
                *self.filter_known_game_keywords(db_checked_keywords),
            ]
        )

    def filter_known_game_keywords(self, keywords: list[str]) -> list[str]:
        candidates = self.normalize_excluded_keywords(keywords)
        if not candidates:
            return []

        from apps.games.models import Game

        known_names = set(
            Game.objects.filter(name__in=candidates).values_list("name", flat=True)
        )
        return [keyword for keyword in candidates if keyword in known_names]

    def clean_direct_game_keyword(self, keyword: str) -> str | None:
        cleaned = keyword.strip(" \n\t.,!?\"'“”‘’()[]{}")
        cleaned = re.sub(r"^(저는|나는|난|제가|내가)\s+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"(처럼|같은|이랑|랑)$", "", cleaned).strip()
        cleaned = re.sub(r"(에서|으로|을|를|은|는|이|가)$", "", cleaned).strip()

        if len(cleaned) < 2:
            return None
        if cleaned in DIRECT_GAME_KEYWORD_STOPWORDS:
            return None
        if len(cleaned.split()) > 4:
            return None
        return cleaned

    def build_conversation_text(self, session: SurveyChatbotSession) -> str:
        messages = session.messages.order_by("sequence")
        return "\n".join(
            f"{message.role}: {message.message}"
            for message in messages
            if message.message
        )

    def _unrelated_count_key(self, session_id: UUID | str) -> str:
        return f"survey:chatbot:unrelated:{session_id}"

    def _lock_key(self, session_id: UUID | str) -> str:
        return f"survey:chatbot:locked:{session_id}"

    def _state_session_key(self, session_id: UUID | str) -> str:
        raw_key = f"survey-chatbot-state:{session_id}"
        return sha256(raw_key.encode()).hexdigest()[:32]

    def _get_state_store(self, session_id: UUID | str):
        return Session.objects.filter(
            session_key=self._state_session_key(session_id),
            expire_date__gt=timezone.now(),
        ).first()

    def _get_state(self, session_id: UUID | str) -> dict[str, Any]:
        store = self._get_state_store(session_id)
        if not store:
            return {}
        return store.get_decoded()

    def _save_state(self, session_id: UUID | str, state: dict[str, Any]) -> None:
        session_key = self._state_session_key(session_id)
        cleaned_state = {
            key: value for key, value in state.items() if value is not None
        }
        if not cleaned_state:
            Session.objects.filter(session_key=session_key).delete()
            return

        Session.objects.update_or_create(
            session_key=session_key,
            defaults={
                "session_data": SessionStore().encode(cleaned_state),
                "expire_date": timezone.now() + timedelta(seconds=UNRELATED_COUNT_TTL),
            },
        )

    def _parse_datetime(self, value: Any) -> timezone.datetime | None:
        if not value:
            return None

        try:
            parsed = timezone.datetime.fromisoformat(str(value))
        except TypeError, ValueError:
            return None

        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def increment_unrelated_attempts(self, session_id: UUID | str) -> int:
        state = self._get_state(session_id)
        now = timezone.now()
        expires_at = self._parse_datetime(state.get("unrelated_count_expires_at"))

        if expires_at is None or expires_at <= now:
            count = 0
        else:
            count = int(state.get("unrelated_count") or 0)

        count += 1
        state["unrelated_count"] = count
        state["unrelated_count_expires_at"] = (
            now + timedelta(seconds=UNRELATED_COUNT_TTL)
        ).isoformat()
        self._save_state(session_id, state)
        return count

    def reset_unrelated_attempts(self, session_id: UUID | str) -> None:
        state = self._get_state(session_id)
        state["unrelated_count"] = None
        state["unrelated_count_expires_at"] = None
        self._save_state(session_id, state)

    def set_lock(self, session_id: UUID | str) -> None:
        unlock_at = timezone.now() + timedelta(seconds=UNRELATED_LOCK_SECONDS)
        state = self._get_state(session_id)
        state["lock_until"] = unlock_at.isoformat()
        self._save_state(session_id, state)

    def get_lock_retry_after_seconds(self, session_id: UUID | str) -> int:
        state = self._get_state(session_id)
        unlock_at = self._parse_datetime(state.get("lock_until"))
        if unlock_at is None:
            if state.get("lock_until") is not None:
                state["lock_until"] = None
                self._save_state(session_id, state)
            return 0

        remaining_seconds = int((unlock_at - timezone.now()).total_seconds())
        if remaining_seconds <= 0:
            state["lock_until"] = None
            self._save_state(session_id, state)
            return 0
        return remaining_seconds
