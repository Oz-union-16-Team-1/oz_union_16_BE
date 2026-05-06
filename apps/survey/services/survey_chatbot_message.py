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
MEANINGLESS_MESSAGE_PATTERNS = (
    r"^[\s\W_]+$",
    r"^[ㄱ-ㅎㅏ-ㅣ\u1100-\u11ff\u3130-\u318f]+$",
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
DIRECT_GAME_KEYWORD_STOPWORDS = {
    "게임",
    "장르",
    "분위기",
    "전투",
    "탐험",
    "성장",
    "승리",
    "에이스",
    "상대",
    "플레이어",
    "ai",
    "보스",
    "보스 몬스터",
    "스토리",
    "캐릭터",
    "스킬",
    "사이트",
    "영역",
    "플레이",
}
EXCLUDED_KEYWORDS_SYSTEM_PROMPT = """
당신은 게임 취향 설문 대화에서 사용자가 직접 언급한 게임명을 추출하는 분석 도우미입니다.

당신의 역할은
추천 결과에서 제외해야 할 게임명을 찾아
일반 텍스트로만 출력하는 것입니다.

---

## 1. 역할 및 목표

사용자가 설문 답변에서 직접 언급한 게임 제목을 추출합니다.
추출된 게임명은 추천 결과 제외 키워드로 사용됩니다.

---

## 2. 추출 기준

- 사용자가 실제로 언급한 게임 제목만 포함합니다.
- 시리즈명이나 게임명으로 볼 수 있는 고유명사만 포함합니다.
- 행동, 장르, 감정, 역할, 상황, 플레이 방식은 포함하지 않습니다.
- 예: `발로란트에서 에이스 할 때`가 있으면 `발로란트`만 출력합니다.
- 게임명이 없으면 `없음`만 출력합니다.

---

## 3. 금지 사항

- 게임명이 아닌 행동을 출력하지 않습니다.
- 장르명, 감정 표현, 플레이 방식, 역할명을 출력하지 않습니다.
- 설명, 마크다운, 코드블록을 출력하지 않습니다.

---

## 4. 출력 규칙

- 게임명만 출력합니다.
- 게임명이 여러 개면 한 줄에 하나씩 출력합니다.
- 쉼표로 나열해도 됩니다.
"""
EXCLUDED_KEYWORDS_USER_PROMPT = """
게임명 추출 요청입니다.

---

## 1. 작업 대상

아래 설문 대화에서 사용자가 직접 언급한 게임명만 일반 텍스트로 출력하세요.

---

## 2. 사용자 답변

{nickname}님 답변:
{user_messages}

---

## 3. 최종 출력

게임명이 있으면 게임명만 출력합니다.
게임명이 없으면 `없음`만 출력합니다.
"""
MIN_SURVEY_QUESTIONS = 3
MAX_SURVEY_QUESTIONS = 5
PREFERENCE_SLOT_REQUIRED_COUNT = 4
PREFERENCE_FUN_FACTOR_SLOTS = {"fun_factor"}
PREFERENCE_PLAY_STYLE_SLOTS = {"pvp_pve", "social_preference"}
PREFERENCE_CONSTRAINT_SLOTS = {
    "difficulty",
    "tempo",
    "session_length",
    "dislike",
}


@dataclass(frozen=True)
class PreferenceSlotDefinition:
    key: str
    label: str
    keywords: tuple[str, ...]


PREFERENCE_SLOT_DEFINITIONS = (
    PreferenceSlotDefinition(
        key="genre_game_type",
        label="선호 장르/게임 타입",
        keywords=(
            "장르",
            "종류",
            "액션",
            "rpg",
            "fps",
            "슈팅",
            "퍼즐",
            "전략",
            "시뮬",
            "레이싱",
            "스포츠",
            "격투",
            "공포",
            "생존",
        ),
    ),
    PreferenceSlotDefinition(
        key="pvp_pve",
        label="PvP/PvE 성향",
        keywords=(
            "pvp",
            "pve",
            "대전",
            "경쟁전",
            "상대",
            "유저",
            "보스",
            "몬스터",
            "레이드",
            "던전",
            "컴퓨터",
        ),
    ),
    PreferenceSlotDefinition(
        key="social_preference",
        label="경쟁/협동/솔로 성향",
        keywords=(
            "경쟁",
            "협동",
            "협력",
            "팀",
            "팀원",
            "친구",
            "혼자",
            "솔로",
            "역할",
            "전술",
        ),
    ),
    PreferenceSlotDefinition(
        key="fun_factor",
        label="핵심 재미 포인트",
        keywords=(
            "피지컬",
            "전략",
            "성장",
            "스토리",
            "탐험",
            "전투",
            "공략",
            "운영",
            "수집",
            "빌드",
            "몰입",
            "성취감",
            "쾌감",
        ),
    ),
    PreferenceSlotDefinition(
        key="difficulty",
        label="난이도 성향",
        keywords=(
            "난이도",
            "어렵",
            "어려운",
            "쉬운",
            "쉽게",
            "편안",
            "하드",
            "도전",
            "압박",
            "긴장",
            "패턴",
            "빡센",
            "캐주얼",
        ),
    ),
    PreferenceSlotDefinition(
        key="tempo",
        label="진행 템포",
        keywords=(
            "빠른",
            "빠르게",
            "천천히",
            "템포",
            "속도",
            "즉각",
            "준비",
            "반응",
            "차근차근",
            "느긋",
        ),
    ),
    PreferenceSlotDefinition(
        key="session_length",
        label="세션 길이",
        keywords=(
            "짧게",
            "짧은",
            "오래",
            "길게",
            "긴 시간",
            "한 판",
            "몇 판",
            "몰아서",
            "접속",
        ),
    ),
    PreferenceSlotDefinition(
        key="dislike",
        label="비선호 요소",
        keywords=(
            "싫",
            "별로",
            "피곤",
            "지루",
            "반복",
            "노가다",
            "스트레스",
            "압박감은",
            "안 좋아",
            "안맞",
        ),
    ),
)


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

            if self.should_complete_session(
                session=session,
                current_step=current_step,
            ):
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

            self.extend_target_question_count_if_needed(
                session=session,
                current_step=current_step,
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

    def is_meaningless_message(self, normalized_message: str) -> bool:
        compact_message = re.sub(r"\s+", "", normalized_message)
        if not compact_message:
            return True
        return any(
            re.fullmatch(pattern, compact_message, flags=re.IGNORECASE)
            for pattern in MEANINGLESS_MESSAGE_PATTERNS
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
        if self.is_meaningless_message(normalized_message):
            return "UNRELATED"
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
        return min(
            MAX_SURVEY_QUESTIONS,
            max(
                MIN_SURVEY_QUESTIONS, self.fallback_target_question_count(user_message)
            ),
        )

    def fallback_target_question_count(self, user_message: str) -> int:
        normalized = user_message.strip()
        if len(normalized) >= 80 or normalized.count(" ") >= 12:
            return 3
        if len(normalized) >= 40 or normalized.count(" ") >= 6:
            return 4
        return 5

    def should_complete_session(
        self,
        session: SurveyChatbotSession,
        current_step: int,
    ) -> bool:
        target_question_count = session.target_question_count or MAX_SURVEY_QUESTIONS
        if current_step >= MAX_SURVEY_QUESTIONS:
            return True
        if current_step < target_question_count:
            return False
        return self.has_sufficient_recommendation_preferences(session)

    def extend_target_question_count_if_needed(
        self,
        session: SurveyChatbotSession,
        current_step: int,
    ) -> None:
        target_question_count = session.target_question_count or MAX_SURVEY_QUESTIONS
        if current_step >= target_question_count:
            session.target_question_count = min(
                MAX_SURVEY_QUESTIONS,
                current_step + 1,
            )

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
        next_preference_slot = self.get_next_preference_slot_label(session)
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
            "next_preference_slot": next_preference_slot,
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
        slot_state = self.build_preference_slot_state(session)
        confirmed_preferences = [
            slot.label
            for slot in PREFERENCE_SLOT_DEFINITIONS
            if slot_state[slot.key] == "confirmed"
        ]
        uncertain_preferences = [
            slot.label
            for slot in PREFERENCE_SLOT_DEFINITIONS
            if slot_state[slot.key] != "confirmed"
        ]
        return (
            ", ".join(confirmed_preferences) if confirmed_preferences else "없음",
            ", ".join(uncertain_preferences) if uncertain_preferences else "없음",
        )

    def build_preference_slot_state(
        self,
        session: SurveyChatbotSession,
    ) -> dict[str, str]:
        confirmed_keys = set()
        uncertain_keys = set()
        for message in session.messages.filter(role=SurveyRoleChoices.USER).values_list(
            "message", flat=True
        ):
            message_slots = self.detect_preference_slots(message)
            if self.is_uncertain_preference_answer(message.strip().lower()):
                uncertain_keys.update(message_slots)
                continue
            confirmed_keys.update(message_slots)

        asked_text = "\n".join(self.get_previous_ai_questions(session))
        uncertain_keys.update(self.detect_preference_slots(asked_text) - confirmed_keys)

        return {
            slot.key: (
                "confirmed"
                if slot.key in confirmed_keys
                else "uncertain" if slot.key in uncertain_keys else "missing"
            )
            for slot in PREFERENCE_SLOT_DEFINITIONS
        }

    def detect_preference_slots(self, text: str) -> set[str]:
        normalized_text = text.lower()
        return {
            slot.key
            for slot in PREFERENCE_SLOT_DEFINITIONS
            if any(keyword.lower() in normalized_text for keyword in slot.keywords)
        }

    def get_next_preference_slot_label(self, session: SurveyChatbotSession) -> str:
        slot_state = self.build_preference_slot_state(session)
        for slot in PREFERENCE_SLOT_DEFINITIONS:
            if slot_state[slot.key] != "confirmed":
                return slot.label
        return "없음"

    def has_sufficient_recommendation_preferences(
        self,
        session: SurveyChatbotSession,
    ) -> bool:
        slot_state = self.build_preference_slot_state(session)
        confirmed_keys = {
            key for key, state in slot_state.items() if state == "confirmed"
        }
        return (
            len(confirmed_keys) >= PREFERENCE_SLOT_REQUIRED_COUNT
            and bool(confirmed_keys & PREFERENCE_FUN_FACTOR_SLOTS)
            and bool(confirmed_keys & PREFERENCE_PLAY_STYLE_SLOTS)
            and bool(confirmed_keys & PREFERENCE_CONSTRAINT_SLOTS)
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
        nickname = self.session_service.get_user_nickname(session.user)
        prompt_values = {
            "nickname": nickname,
            "user_messages": "\n".join(f"- {message}" for message in user_messages),
        }
        system_prompt = SURVEY_CHATBOT_SUMMARY_SYSTEM_PROMPT.strip().format(
            **prompt_values
        )
        prompt = SURVEY_CHATBOT_SUMMARY_USER_PROMPT.strip().format(**prompt_values)

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
                return survey_answer or "", self.generate_excluded_keywords_with_llm(
                    user_messages=user_messages,
                    nickname=nickname,
                )

        fallback_summary = self.build_fallback_summary(user_messages)
        if fallback_summary:
            return fallback_summary, self.generate_excluded_keywords_with_llm(
                user_messages=user_messages,
                nickname=nickname,
            )

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
        sentences = self.build_slot_based_fallback_summary_sentences(joined)
        if sentences:
            return " ".join(sentences)

        return "게임 취향과 관련된 답변을 제공했지만 구체적인 추천 기준은 충분히 정리되지 않았습니다."

    def build_slot_based_fallback_summary_sentences(self, text: str) -> list[str]:
        sentences = []
        normalized_text = text.lower()

        genre_label = self.extract_fallback_genre_label(normalized_text)
        if genre_label:
            sentences.append(f"{genre_label} 장르나 게임 유형에 관심을 보입니다.")

        if any(keyword in normalized_text for keyword in ("ai", "컴퓨터")) and any(
            keyword in normalized_text
            for keyword in ("못 느껴", "재미를 못", "큰 재미")
        ):
            sentences.append(
                "AI 상대보다 다른 플레이어와 겨루는 PvP 플레이에서 더 큰 재미를 느끼는 편입니다."
            )
        elif any(
            keyword in normalized_text
            for keyword in ("pvp", "대전", "경쟁전", "상대", "플레이어", "유저")
        ):
            sentences.append("다른 플레이어와 겨루는 PvP 플레이를 선호합니다.")
        elif any(
            keyword in normalized_text
            for keyword in ("pve", "보스", "몬스터", "레이드", "던전")
        ):
            sentences.append("보스나 몬스터를 공략하는 PvE 플레이에 관심이 있습니다.")

        if any(
            keyword in normalized_text
            for keyword in ("팀", "팀원", "협력", "협동", "전략을 짜", "전술")
        ):
            sentences.append("팀원과 전략을 짜고 협력하는 플레이를 선호합니다.")
        elif any(keyword in normalized_text for keyword in ("혼자", "솔로")):
            sentences.append("혼자 몰입해서 진행하는 플레이를 선호합니다.")

        fun_factors = self.extract_fallback_fun_factor_labels(normalized_text)
        if fun_factors:
            sentences.append(
                f"{', '.join(fun_factors)} 중심의 재미 요소를 중요하게 여깁니다."
            )

        if any(keyword in normalized_text for keyword in ("편안", "쉽게", "쉬운")):
            sentences.append("편안하고 쉽게 즐길 수 있는 난이도를 선호합니다.")
        elif any(
            keyword in normalized_text
            for keyword in ("어렵", "어려운", "하드", "도전", "긴장", "압박", "빡센")
        ):
            sentences.append("도전적이거나 긴장감 있는 난이도에도 흥미를 보입니다.")

        return sentences

    def extract_fallback_genre_label(self, normalized_text: str) -> str | None:
        genre_keywords = (
            ("fps", "FPS"),
            ("슈팅", "슈팅"),
            ("rpg", "RPG"),
            ("격투", "격투"),
            ("액션", "액션"),
            ("전략", "전략"),
            ("퍼즐", "퍼즐"),
            ("레이싱", "레이싱"),
            ("스포츠", "스포츠"),
            ("시뮬", "시뮬레이션"),
        )
        for keyword, label in genre_keywords:
            if keyword in normalized_text:
                return label
        return None

    def extract_fallback_fun_factor_labels(self, normalized_text: str) -> list[str]:
        factor_keywords = (
            ("피지컬", "피지컬"),
            ("전략", "전략"),
            ("성장", "성장"),
            ("스토리", "스토리"),
            ("탐험", "탐험"),
            ("전투", "전투"),
            ("공략", "공략"),
            ("에이스", "실력 발휘"),
            ("쾌감", "성취감"),
            ("성취감", "성취감"),
        )
        labels = []
        seen_labels = set()
        for keyword, label in factor_keywords:
            if keyword in normalized_text and label not in seen_labels:
                seen_labels.add(label)
                labels.append(label)
        return labels[:3]

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

    def generate_excluded_keywords_with_llm(
        self,
        *,
        user_messages: list[str],
        nickname: str,
    ) -> list[str]:
        if not any(message.strip() for message in user_messages):
            return []

        prompt_values = {
            "nickname": nickname,
            "user_messages": "\n".join(f"- {message}" for message in user_messages),
        }
        response = self.session_service.generate_question_with_llm(
            EXCLUDED_KEYWORDS_USER_PROMPT.strip().format(**prompt_values),
            system_prompt=EXCLUDED_KEYWORDS_SYSTEM_PROMPT.strip(),
            temperature=0.1,
        )
        if not response:
            return []

        return self.parse_excluded_keywords_response(response)

    def parse_excluded_keywords_response(self, response: str) -> list[str]:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("text\n", "", 1).strip()

        if not cleaned or cleaned.lower() in {"none", "null"} or cleaned == "없음":
            return []
        if cleaned.startswith(("{", "[")):
            return []

        keywords: list[str] = []
        for line in cleaned.splitlines():
            normalized_line = re.sub(r"^[-*\d.)\s]+", "", line).strip()
            if not normalized_line:
                continue
            keywords.extend(
                keyword.strip()
                for keyword in re.split(r"[,，/]", normalized_line)
                if keyword.strip()
            )

        return self.normalize_excluded_keywords(keywords)

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
