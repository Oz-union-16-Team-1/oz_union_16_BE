import logging
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import APIException

from apps.survey.choices import (
    ChatbotModelChoices,
    SurveyRoleChoices,
    SurveyStatusChoices,
)
from apps.survey.models import SurveyChatbotMessage, SurveyChatbotSession
from apps.survey.prompts.survey_chatbot_prompt import SURVEY_CHATBOT_PROMPT

SURVEY_COMPLETION_MESSAGE = (
    "설문이 종료되었습니다 추천 게임 보기 버튼을 클릭해서 추천된 게임을 확인해보세요!"
)


class SurveyQuestionGenerationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "설문 첫 질문을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
    default_code = "survey_question_generation_unavailable"


@dataclass(frozen=True)
class SurveyChatbotSessionCreateResult:
    session_id: str
    status: str
    ai_question: str
    progress: dict
    recommendation_ready: bool = False

    def as_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "ai_question": self.ai_question,
            "progress": self.progress,
            "recommendation_ready": self.recommendation_ready,
        }


class SurveyChatbotSessionService:
    QUESTION_ENDINGS = (
        "요?",
        "나요?",
        "까요?",
        "주세요.",
        "주세요",
        "말해주세요.",
        "말해주세요",
        "가요?",
        "가요",
        "인가요?",
        "인가요",
        "한가요?",
        "한가요",
    )
    YES_NO_STYLE_ENDINGS = (
        "좋아하시나요?",
        "좋아하시나요",
        "선호하시나요?",
        "선호하시나요",
        "즐거우신가요?",
        "즐거우신가요",
    )
    OPEN_ENDED_QUESTION_HINTS = (
        "어떤",
        "무슨",
        "왜",
        "어떻게",
        "어느",
        "무엇",
        "이유",
        "설명",
        "이야기",
        "알려",
        "떠올렸을 때",
    )
    COMPARISON_QUESTION_HINTS = (
        "중 어느",
        "중 어떤",
        "어느 쪽",
        "어떤 쪽",
        "더 선호",
        "더 좋",
        "비교하면",
    )
    QUESTION_GENERATION_MAX_ATTEMPTS = 3

    # 유저별 설문 세션 생성 또는 기존 세션 재사용
    def create_session(
        self, user: Any, is_reset: bool = False
    ) -> SurveyChatbotSessionCreateResult:
        with transaction.atomic():
            if is_reset:
                self.delete_user_session(user)

            session, created = self.get_or_create_user_session(user)

            if self.should_initialize_session(session, created):
                self.initialize_session(session)

            question = self.get_current_question(session)

        return SurveyChatbotSessionCreateResult(
            session_id=str(session.id),
            status=session.status,
            ai_question=question,
            progress=self.build_progress(session),
            recommendation_ready=session.status == SurveyStatusChoices.CLOSED,
        )

    # 유저당 하나의 설문 세션만 유지하도록 세션을 조회하거나 생성
    def get_or_create_user_session(
        self, user: Any
    ) -> tuple[SurveyChatbotSession, bool]:
        return SurveyChatbotSession.objects.select_for_update().get_or_create(
            user=user,
            defaults={
                "using_model": ChatbotModelChoices.GEMINI_2_5_FLASH,
                "status": SurveyStatusChoices.OPEN,
            },
        )

    # 설문을 다시 시작할 때 기존 세션 삭제
    def delete_user_session(self, user: Any) -> None:
        SurveyChatbotSession.objects.select_for_update().filter(user=user).delete()

    # 현재 세션을 초기화해야 하는 상황인지 판단
    def should_initialize_session(
        self,
        session: SurveyChatbotSession,
        created: bool,
    ) -> bool:
        return created or not session.messages.exists()

    # 설문 세션을 초기 상태로 되돌리고 첫 질문 저장
    def initialize_session(self, session: SurveyChatbotSession) -> None:
        self.clear_session(session)
        session.status = SurveyStatusChoices.OPEN
        session.target_question_count = None
        session.using_model = ChatbotModelChoices.GEMINI_2_5_FLASH
        session.save(update_fields=["status", "target_question_count", "using_model"])

        SurveyChatbotMessage.objects.create(
            session=session,
            message=self.generate_first_question(),
            role=SurveyRoleChoices.AI,
            sequence=1,
        )

    # 설문 메시지와 결과를 지워 세션을 비움
    def clear_session(self, session: SurveyChatbotSession) -> None:
        session.messages.all().delete()
        if hasattr(session, "results"):
            session.results.delete()

    # 현재 세션에서 유저에게 보여줄 마지막 AI 질문을 가져옴
    def get_current_question(self, session: SurveyChatbotSession) -> str:
        if session.status == SurveyStatusChoices.CLOSED:
            return SURVEY_COMPLETION_MESSAGE

        message = (
            session.messages.filter(role=SurveyRoleChoices.AI)
            .order_by("-sequence")
            .first()
        )
        return message.message if message else self.generate_first_question()

    # 유저 답변 수 기준으로 설문 진행도 계산
    def build_progress(self, session: SurveyChatbotSession) -> dict:
        current_step = session.messages.filter(role=SurveyRoleChoices.USER).count()
        total_steps = session.target_question_count
        completion_rate = round(current_step / total_steps, 2) if total_steps else None

        return {
            "current_step": current_step,
            "total_steps": total_steps,
            "completion_rate": completion_rate,
        }

    # 첫 질문 생성 실패 시 최대 3회까지 다시 시도
    def generate_first_question(self) -> str:
        prompt = self.build_first_question_prompt()
        question = self.generate_valid_question(
            prompt=prompt,
            temperature=0.85,
            log_message="Invalid survey question generated by LLM: %s",
        )
        if question:
            return question
        raise SurveyQuestionGenerationUnavailable()

    # Gemini에게 질문 생성을 요청하고 텍스트 응답 추출
    def generate_question_with_llm(
        self,
        prompt: str,
        temperature: float = 0.4,
    ) -> str | None:
        api_key = settings.SURVEY_CHATBOT_GEMINI_API_KEY
        if not api_key:
            return None

        url = (
            f"{settings.SURVEY_CHATBOT_GEMINI_BASE_URL}/v1beta/models/"
            f"{settings.SURVEY_CHATBOT_GEMINI_MODEL}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 1024,
                "responseMimeType": "text/plain",
            },
        }
        try:
            response = requests.post(
                url,
                params={"key": api_key},
                json=payload,
                timeout=settings.SURVEY_CHATBOT_GEMINI_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException:
            logging.getLogger(__name__).exception(
                "Failed to generate survey chatbot question."
            )
            return None

        response_data = response.json()
        question = self.extract_text_from_gemini_response(response_data)
        if not question:
            logging.getLogger(__name__).warning(
                "Empty Gemini response for survey question: %s", response_data
            )
        return question

    # 질문 생성 실패 시 재시도, 유효한 질문만 반환
    def generate_valid_question(
        self,
        prompt: str,
        temperature: float,
        log_message: str,
    ) -> str | None:
        logger = logging.getLogger(__name__)
        for _ in range(self.QUESTION_GENERATION_MAX_ATTEMPTS):
            question = self.generate_question_with_llm(
                prompt,
                temperature=temperature,
            )
            if question and self.is_valid_survey_question(question):
                return question
            logger.warning(log_message, question)
        return None

    # Gemini 응답의 여러 parts를 하나의 질문으로 결합
    def extract_text_from_gemini_response(self, data: dict) -> str | None:
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except KeyError, IndexError, TypeError:
            return None

        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        text = text.strip()
        return text or None

    # 첫 질문/후속 질문이 문장 형태로 완성됐는지 검사
    def is_complete_first_question(self, question: str | None) -> bool:
        if not question:
            return False

        question = question.strip()
        return (
            40 <= len(question) <= 120
            and question.endswith(self.QUESTION_ENDINGS)
            and (
                any(hint in question for hint in self.OPEN_ENDED_QUESTION_HINTS)
                or any(hint in question for hint in self.COMPARISON_QUESTION_HINTS)
            )
        )

    # 예/아니오형 질문을 막되 A/B 비교형 질문은 허용
    def is_valid_survey_question(self, question: str | None) -> bool:
        if not self.is_complete_first_question(question):
            return False

        assert question is not None
        normalized = question.strip()
        is_comparison_question = any(
            hint in normalized for hint in self.COMPARISON_QUESTION_HINTS
        )
        if not is_comparison_question and normalized.endswith(
            self.YES_NO_STYLE_ENDINGS
        ):
            return False

        return True

    # 첫 질문 생성에 사용할 기본 프롬프트를 호출
    def load_first_question_prompt(self) -> str:
        return SURVEY_CHATBOT_PROMPT.strip()

    # 첫 질문 생성 프롬프트를 그대로 사용해 프롬프트 파일의 계약을 보존
    def build_first_question_prompt(self) -> str:
        return self.load_first_question_prompt()
