import logging
import re
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
from apps.survey.prompts.survey_chatbot_prompt import (
    SURVEY_CHATBOT_SYSTEM_PROMPT,
    SURVEY_CHATBOT_USER_PROMPT,
)

SURVEY_COMPLETION_MESSAGE = (
    "설문이 종료되었습니다 아래의 버튼을 클릭해서 추천된 게임을 확인해보세요!"
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
    QUESTION_MAX_LENGTH = 100
    QUESTION_GENERATION_MAX_ATTEMPTS = 3
    SAFE_FALLBACK_QUESTIONS = (
        "{nickname}님은 혼자 편하게 몰입하는 플레이와 다른 사람과 함께하는 플레이 중 어느 쪽이 더 잘 맞는지 편하게 말씀해 주세요.",
        "{nickname}님은 빠르게 반응하는 플레이와 차근차근 계획하는 플레이 중 어느 쪽이 더 끌리는지 말씀해 주세요.",
        "{nickname}님은 어려운 도전을 넘는 플레이와 부담 없이 즐기는 플레이 중 어느 쪽이 더 편한지 말씀해 주세요.",
    )
    SAFE_NEXT_FALLBACK_QUESTIONS = (
        "{nickname}님은 방금 말한 취향이 빠르게 판단하는 쪽과 차근차근 준비하는 쪽 중 어디에 더 가까운지 편하게 말씀해 주세요.",
        "{nickname}님은 비슷한 게임에서 직접 앞에서 이끄는 플레이와 상황을 보며 돕는 플레이 중 어느 쪽이 더 잘 맞나요?",
        "{nickname}님은 실력이 늘어 이기는 재미와 새로운 요소를 발견하는 재미 중 어느 쪽이 더 크게 느껴지나요?",
    )
    SAFE_REASK_FALLBACK_QUESTIONS = (
        "{nickname}님은 혼자 하는 플레이와 함께하는 플레이 중 어느 쪽이 더 편한지 가볍게 골라 말씀해 주세요.",
        "{nickname}님은 빠른 진행과 느긋한 진행 중 어느 쪽이 더 편한지 편하게 알려주세요.",
    )
    SAFE_CLARIFY_FALLBACK_QUESTIONS = (
        "쉽게 말해, {nickname}님은 혼자 즐기는 게임과 함께 즐기는 게임 중 어느 쪽이 더 편한지 말씀해 주세요.",
        "질문을 바꿔서 물어볼게요. {nickname}님은 빠르게 판단하는 게임과 천천히 계획하는 게임 중 어느 쪽이 더 잘 맞나요?",
    )
    CONTEXTUAL_NEXT_FALLBACK_RULES = (
        (
            "슈팅",
            ("슈팅", "fps", "에임", "총", "교전", "사이트", "스파이크", "에이스"),
            "{nickname}님은 슈팅 게임에서 직접 진입하는 역할과 정보를 보고 마무리하는 역할 중 어느 쪽이 더 편한지 말씀해 주세요.",
        ),
        (
            "전술",
            ("전술", "전략", "팀", "역할", "포지션", "진입", "수비", "공격"),
            "{nickname}님은 정해진 역할을 정확히 수행하는 방식과 상황에 맞춰 판단을 바꾸는 방식 중 어느 쪽이 더 맞나요?",
        ),
        (
            "모바(MOBA)",
            ("moba", "모바", "라인", "한타", "갱", "오브젝트", "로밍"),
            "{nickname}님은 팀 싸움에서 먼저 교전을 여는 역할과 흐름을 보고 합류하는 역할 중 어느 쪽이 더 편한지 말씀해 주세요.",
        ),
        (
            "실시간 전략",
            ("rts", "실시간 전략", "빌드오더", "멀티태스킹", "자원", "유닛"),
            "{nickname}님은 빠른 자원 관리와 상대 움직임에 맞춘 병력 운용 중 어느 쪽이 더 중요한지 말씀해 주세요.",
        ),
        (
            "턴제 전략",
            ("턴제", "tbs", "턴", "수읽기", "행동력", "배치"),
            "{nickname}님은 안전하게 계산하는 선택과 위험을 감수한 큰 선택 중 어느 쪽이 더 끌리는지 말씀해 주세요.",
        ),
        (
            "전략",
            ("전략", "운영", "계획", "판단", "상황 판단", "전술"),
            "{nickname}님은 미리 세운 계획대로 풀어가는 방식과 예상 밖 상황에 맞춰 바꾸는 방식 중 어느 쪽이 더 좋으신가요?",
        ),
        (
            "격투",
            ("격투", "콤보", "심리전", "반격", "카운터", "잡기"),
            "{nickname}님은 상대 패턴을 읽고 반격하는 플레이와 연습한 콤보를 정확히 성공시키는 플레이 중 어느 쪽이 더 좋으신가요?",
        ),
        (
            "액션",
            ("액션", "회피", "공격", "타격", "전투", "손맛", "피지컬"),
            "{nickname}님은 빠르게 반응해 위기를 넘기는 플레이와 공격 흐름을 만들며 밀어붙이는 플레이 중 어느 쪽이 더 맞나요?",
        ),
        (
            "핵 앤 슬래시",
            ("핵앤슬래시", "핵 앤 슬래시", "쓸어버", "몰이", "파밍", "스킬 빌드"),
            "{nickname}님은 강한 스킬로 몰아치는 플레이와 장비나 빌드를 맞춰 효율을 높이는 플레이 중 어느 쪽이 더 좋으신가요?",
        ),
        (
            "RPG",
            ("rpg", "역할수행", "성장", "레벨", "장비", "빌드", "보스", "퀘스트"),
            "{nickname}님은 어려운 적을 공략하는 재미와 장비나 빌드를 준비해 강해지는 재미 중 어느 쪽이 더 중요한지 말씀해 주세요.",
        ),
        (
            "어드벤처",
            ("어드벤처", "탐험", "발견", "단서", "지역", "모험"),
            "{nickname}님은 숨겨진 장소를 자유롭게 찾는 탐험과 단서를 따라 세계를 이해하는 진행 중 어느 쪽이 더 끌리는지 말씀해 주세요.",
        ),
        (
            "포인트 앤 클릭",
            ("포인트", "클릭", "단서", "조사", "추리", "상호작용"),
            "{nickname}님은 사물을 꼼꼼히 조사하는 방식과 연결된 단서를 추리해 답을 찾는 방식 중 어느 쪽이 더 맞나요?",
        ),
        (
            "퍼즐",
            ("퍼즐", "규칙", "문제", "논리", "해답", "두뇌"),
            "{nickname}님은 규칙을 차근차근 파악하는 퍼즐과 막힌 해답을 떠올려 푸는 퍼즐 중 어느 쪽이 더 좋으신가요?",
        ),
        (
            "퀴즈/상식",
            ("퀴즈", "상식", "문제 맞히", "정답", "지식"),
            "{nickname}님은 알고 있는 지식을 바로 쓰는 방식과 힌트를 보고 추론하는 방식 중 어느 쪽이 더 재미있는지 말씀해 주세요.",
        ),
        (
            "시뮬레이션",
            ("시뮬", "시뮬레이션", "관리", "운영", "효율", "루틴"),
            "{nickname}님은 시스템을 효율적으로 관리하는 방식과 직접 세운 루틴을 안정적으로 굴리는 방식 중 어느 쪽이 더 맞나요?",
        ),
        (
            "스포츠",
            ("스포츠", "경기", "선수", "팀 운영", "시합", "득점"),
            "{nickname}님은 직접 조작으로 득점하는 플레이와 팀 운영이나 전술 선택으로 이기는 플레이 중 어느 쪽이 더 좋으신가요?",
        ),
        (
            "레이싱",
            ("레이싱", "주행", "코스", "기록", "드리프트", "속도"),
            "{nickname}님은 코스를 익혀 기록을 줄이는 플레이와 순간 조작으로 위기를 넘기는 플레이 중 어느 쪽이 더 끌리는지 말씀해 주세요.",
        ),
        (
            "플랫폼",
            ("플랫폼", "점프", "타이밍", "발판", "조작", "구간"),
            "{nickname}님은 정확한 타이밍으로 넘기는 플레이와 반복 연습으로 조작을 익히는 플레이 중 어느 쪽이 더 맞나요?",
        ),
        (
            "음악",
            ("음악", "리듬", "박자", "노트", "정확도", "연주"),
            "{nickname}님은 박자를 정확히 따라가는 플레이와 어려운 구간을 반복 연습하는 플레이 중 어느 쪽이 더 좋으신가요?",
        ),
        (
            "핀볼",
            ("핀볼", "공", "플리퍼", "점수", "반사"),
            "{nickname}님은 공의 흐름을 예측해 조작하는 재미와 우연한 연쇄 반응이 이어지는 재미 중 어느 쪽이 더 끌리는지 말씀해 주세요.",
        ),
        (
            "아케이드",
            ("아케이드", "점수", "콤보", "라운드", "짧게", "반복"),
            "{nickname}님은 점수를 조금씩 높이는 반복 플레이와 즉각적인 조작으로 결과가 나는 플레이 중 어느 쪽이 더 맞나요?",
        ),
        (
            "인디",
            ("인디", "독특", "실험적", "개성", "소규모"),
            "{nickname}님은 낯선 규칙을 발견하는 재미와 독특한 분위기나 표현 방식에 몰입하는 재미 중 어느 쪽이 더 좋으신가요?",
        ),
        (
            "비주얼 노벨",
            ("비주얼노벨", "비주얼 노벨", "선택지", "캐릭터 관계", "분기", "감정선"),
            "{nickname}님은 캐릭터 관계가 깊어지는 이야기와 선택에 따라 다른 결말을 확인하는 이야기 중 어느 쪽이 더 끌리나요?",
        ),
        (
            "카드 및 보드 게임",
            ("카드", "보드", "덱", "수읽기", "패", "카드 조합"),
            "{nickname}님은 덱이나 조합을 미리 준비하는 플레이와 상대 선택을 읽고 대응하는 플레이 중 어느 쪽이 더 맞나요?",
        ),
    )
    QUESTION_ENDINGS = (
        "?",
        ".",
        "요.",
        "요?",
        "나요?",
        "까요?",
        "주세요.",
        "말해주세요.",
        "가요",
        "가요?",
        "인가요",
        "인가요?",
        "한가요",
        "한가요?",
    )
    FIRST_QUESTION_ENDINGS = (
        "?",
        ".",
        "요.",
        "요?",
        "나요?",
        "까요?",
        "가요",
        "가요?",
        "인가요",
        "인가요?",
        "한가요",
        "한가요?",
        "있나요",
        "있나요?",
        "주세요.",
        "말씀해 주세요.",
    )
    YES_NO_STYLE_ENDINGS = (
        "좋아하시나요?",
        "선호하시나요?",
        "즐거우신가요?",
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
    )
    VAGUE_QUESTION_PATTERNS = (
        r"어떤\s*점",
        r"어떤\s*부분",
        r"어떤\s*요소",
        r"어떤\s*게임\s*스타일",
        r"어떤\s*스타일",
        r"왜\s*좋",
        r"무엇을\s*중요",
        r"자세히\s*말씀해\s*주세요",
    )
    GENERIC_QUESTION_PATTERNS = (
        r"게임에서\s*무엇을\s*중요하게",
        r"게임할\s*때\s*어떤\s*스타일",
        r"어떤\s*플레이\s*방식.*좋",
        r"어떤\s*게임.*좋",
    )
    QUESTION_SIMILARITY_STOPWORDS = {
        "어떤",
        "무슨",
        "게임",
        "플레이",
        "방식",
        "스타일",
        "좋아",
        "선호",
        "말씀",
        "알려",
        "주세요",
        "있나요",
        "느끼시나요",
        "끌리나요",
        "경험",
        "부분",
        "요소",
    }
    QUESTION_TOPIC_KEYWORDS = {
        "genre": ("장르", "종류", "액션", "RPG", "FPS", "퍼즐", "전략", "시뮬레이션"),
        "difficulty": ("난이도", "어렵", "쉬운", "도전", "하드", "패턴", "보스"),
        "coop_competition": ("협력", "협동", "경쟁", "팀", "친구", "역할", "대결"),
        "story": ("스토리", "서사", "세계관", "몰입", "캐릭터", "감정"),
        "combat": ("전투", "공격", "수비", "반응", "콤보", "제압", "싸우"),
        "exploration": ("탐험", "발견", "지역", "숨겨진", "비밀", "맵"),
        "growth": ("성장", "레벨", "빌드", "장비", "파밍", "강해"),
        "tempo": ("빠른", "천천히", "템포", "속도", "준비", "진행"),
        "reward": ("보상", "수집", "아이템", "획득", "드롭"),
        "mastery": ("숙련", "실력", "연습", "익히", "운용"),
    }

    # 유저별 설문 세션 생성 또는 기존 세션 재사용
    def create_session(self, user: Any) -> SurveyChatbotSessionCreateResult:
        with transaction.atomic():
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

    def reset_session(self, user: Any) -> SurveyChatbotSessionCreateResult:
        with transaction.atomic():
            self.delete_user_session(user)
            session, _ = self.get_or_create_user_session(user)
            self.initialize_session(session)
            question = self.get_current_question(session)

        return SurveyChatbotSessionCreateResult(
            session_id=str(session.id),
            status=session.status,
            ai_question=question,
            progress=self.build_progress(session),
            recommendation_ready=False,
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
            message=self.generate_first_question(session.user),
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
        return (
            message.message if message else self.generate_first_question(session.user)
        )

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

    # 첫 질문 생성 실패 시 안전한 기본 질문으로 설문 진행을 유지
    def generate_first_question(self, user: Any | None = None) -> str:
        nickname = self.get_user_nickname(user) if user else None
        system_prompt, user_prompt = self.build_first_question_prompts(user)
        question = self.generate_valid_question(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.85,
            log_message="Invalid survey question generated by LLM: %s",
            mode="FIRST",
            fallback_questions=self.SAFE_FALLBACK_QUESTIONS,
            nickname=nickname,
        )
        if question:
            return question
        return self.SAFE_FALLBACK_QUESTIONS[0]

    # Gemini에게 질문 생성을 요청하고 텍스트 응답 추출
    def generate_question_with_llm(
        self,
        prompt: str,
        temperature: float = 0.4,
        system_prompt: str | None = None,
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
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}],
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
                "Empty Gemini response for survey question. finish_reason=%s prompt_feedback=%s response=%s",
                self.get_gemini_finish_reason(response_data),
                response_data.get("promptFeedback"),
                response_data,
            )
        return question

    # LLM 질문 생성은 최대 3회 시도하고, 모두 실패하면 fallback으로 진행
    def generate_valid_question(
        self,
        prompt: str,
        temperature: float,
        log_message: str,
        system_prompt: str | None = None,
        mode: str = "FIRST",
        previous_questions: list[str] | None = None,
        latest_user_message: str = "",
        fallback_questions: tuple[str, ...] | None = None,
        nickname: str | None = None,
    ) -> str | None:
        logger = logging.getLogger(__name__)
        question = None
        for attempt in range(self.QUESTION_GENERATION_MAX_ATTEMPTS):
            retry_system_prompt, retry_prompt = self.build_retry_question_prompts(
                original_system_prompt=system_prompt,
                original_prompt=prompt,
                attempt=attempt,
                mode=mode,
                nickname=nickname or "사용자",
                latest_user_message=latest_user_message,
            )
            question = self.generate_question_with_llm(
                retry_prompt,
                temperature=temperature if attempt == 0 else min(temperature, 0.3),
                system_prompt=retry_system_prompt,
            )
            question = self.normalize_generated_question(question)
            question = self.ensure_nickname_in_question(question, nickname)
            question = self.repair_yes_no_question(question)
            question = self.repair_incomplete_question_ending(question)
            question = self.polish_generated_question(question)
            if question and self.is_valid_survey_question(
                question=question,
                mode=mode,
                previous_questions=previous_questions,
                latest_user_message=latest_user_message,
            ):
                return question

            logger.warning(log_message, question)

        return self.get_safe_fallback_question(
            mode=mode,
            previous_questions=previous_questions or [],
            fallback_questions=fallback_questions,
            latest_user_message=latest_user_message,
            nickname=nickname or "사용자",
        )

    def build_retry_question_prompts(
        self,
        original_system_prompt: str | None,
        original_prompt: str,
        attempt: int,
        mode: str,
        nickname: str,
        latest_user_message: str,
    ) -> tuple[str | None, str]:
        if attempt == 0:
            return original_system_prompt, original_prompt

        system_prompt = (
            "당신은 게임 추천 설문용 질문을 만드는 챗봇입니다. "
            "한국어 질문 한 문장만 출력하세요. 설명, 번호, 따옴표는 출력하지 마세요."
        )
        if attempt == 1:
            prompt = (
                f"{nickname}님에게 물어볼 게임 취향 질문을 한 문장으로 작성하세요.\n"
                f"작업 유형: {mode}\n"
                f"직전 사용자 답변: {latest_user_message or '없음'}\n"
                "조건:\n"
                f"- 반드시 '{nickname}님'을 포함합니다.\n"
                "- 100자 이내로 작성합니다.\n"
                "- 게임 추천에 필요한 취향 축을 하나 확인합니다.\n"
                "- 자연스럽고 편하게 답할 수 있는 질문으로 작성합니다.\n"
                "- 경험을 깊게 캐묻지 않습니다.\n"
                "질문 한 문장만 출력하세요."
            )
            return system_prompt, prompt

        prompt = (
            "아래 질문 문장을 그대로 출력하세요.\n"
            f"{nickname}님은 혼자/협동/경쟁, 피지컬/전략, 쉬움/어려움 중 "
            "어떤 기준이 게임을 고를 때 더 중요한지 편하게 말씀해 주세요."
        )
        return system_prompt, prompt

    def ensure_nickname_in_question(
        self,
        question: str | None,
        nickname: str | None,
    ) -> str | None:
        if not question or not nickname or f"{nickname}님" in question:
            return question
        return f"{nickname}님은 {question}"

    def normalize_generated_question(self, question: str | None) -> str | None:
        if not question:
            return None

        normalized = " ".join(question.strip().strip('"').strip("'").split())
        return normalized or None

    def repair_yes_no_question(self, question: str | None) -> str | None:
        return question

    def polish_generated_question(self, question: str | None) -> str | None:
        if not question:
            return None

        polished = question
        replacements = (
            (r"더\s*흥미를\s*느끼는\s*쪽인지", "더 흥미를 느끼는지"),
            (r"흥미를\s*느끼는\s*쪽인지", "흥미를 느끼는지"),
            (r"더\s*끌리는\s*쪽인지", "더 끌리는지"),
            (r"끌리는\s*쪽인지", "끌리는지"),
            (r"더\s*잘\s*맞는\s*쪽인지", "더 잘 맞는지"),
            (r"잘\s*맞는\s*쪽인지", "잘 맞는지"),
            (r"더\s*편한\s*쪽인지", "더 편한지"),
            (r"편한\s*쪽인지", "편한지"),
            (r"선호하는\s*쪽인지", "선호하는지"),
            (r"좋아하는\s*쪽인지", "좋아하는지"),
            (r"즐겁게\s*느끼는\s*쪽인지", "즐겁게 느끼는지"),
            (r"느끼는\s*쪽인지", "느끼는지"),
        )
        for pattern, replacement in replacements:
            polished = re.sub(pattern, replacement, polished)

        polished = re.sub(r"\s+", " ", polished).strip()
        return polished or None

    def repair_incomplete_question_ending(self, question: str | None) -> str | None:
        if not question:
            return None

        normalized = question.rstrip()
        if normalized.endswith("신가"):
            return f"{normalized}요?"
        if normalized.endswith(self.QUESTION_ENDINGS):
            return normalized
        if len(normalized) < 30:
            return normalized

        dangling_patterns = (
            r"\s*중\s*어떤\s*$",
            r"\s*중\s*어느\s*$",
            r"\s*중\s*어떤\s*것을\s*더\s*선(?:호)?\s*$",
            r"\s*중\s*어떤\s*것이\s*더\s*선(?:호)?\s*$",
            r"\s*중\s*어떤\s*것이\s*더\s*$",
            r"\s*중\s*어떤\s*것을\s*더\s*$",
            r"\s*중\s*어느\s*쪽이\s*더\s*$",
        )
        for pattern in dangling_patterns:
            if re.search(pattern, normalized):
                normalized = re.sub(pattern, "", normalized).rstrip(" ,，")
                return f"{normalized} 중 어느 쪽이 더 잘 맞는지 편하게 말씀해 주세요."

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

    def get_gemini_finish_reason(self, data: dict) -> str | None:
        try:
            return data["candidates"][0].get("finishReason")
        except KeyError, IndexError, TypeError:
            return None

    # 첫 질문/후속 질문이 문장 형태로 완성됐는지 검사
    def is_complete_first_question(self, question: str | None) -> bool:
        if not question:
            return False

        question = question.strip()
        return self.is_complete_question_text(
            question=question,
            endings=self.FIRST_QUESTION_ENDINGS,
        )

    def is_complete_survey_question(
        self,
        question: str | None,
        mode: str = "FIRST",
    ) -> bool:
        if mode == "FIRST":
            return self.is_complete_first_question(question)
        if not question:
            return False

        return self.is_complete_question_text(
            question=question,
            endings=self.QUESTION_ENDINGS,
        )

    def is_complete_question_text(
        self,
        question: str | None,
        endings: tuple[str, ...],
    ) -> bool:
        if not question:
            return False

        question = question.strip()
        if not 10 <= len(question) <= self.QUESTION_MAX_LENGTH:
            return False
        if question.endswith(endings):
            return True
        return not self.looks_cut_off_question(question)

    def looks_cut_off_question(self, question: str) -> bool:
        cut_off_endings = (
            "생각하시",
            "중 어떤",
            "중 어느",
            "어떤 것을 더",
            "어떤 것이 더",
            "어느 쪽이 더",
            "더 선",
            "더 좋",
            "더 끌",
            "더 맞",
            "인상",
        )
        return question.endswith(cut_off_endings)

    # 설문 진행을 막지 않도록 최소 조건만 검증
    def is_valid_survey_question(
        self,
        question: str | None,
        mode: str = "FIRST",
        previous_questions: list[str] | None = None,
        latest_user_message: str = "",
    ) -> bool:
        if not self.is_complete_survey_question(question=question, mode=mode):
            return False

        return True

    def is_low_quality_question(self, question: str) -> bool:
        return any(
            re.search(pattern, question) for pattern in self.VAGUE_QUESTION_PATTERNS
        ) or any(
            re.search(pattern, question) for pattern in self.GENERIC_QUESTION_PATTERNS
        )

    def is_repeated_question(
        self,
        question: str,
        previous_questions: list[str],
    ) -> bool:
        return any(
            self.is_question_too_similar(question, previous_question)
            for previous_question in previous_questions
        )

    def is_question_too_similar(self, question: str, previous_question: str) -> bool:
        if question.strip() == previous_question.strip():
            return True

        question_tokens = self.extract_question_tokens(question)
        previous_tokens = self.extract_question_tokens(previous_question)
        if not question_tokens or not previous_tokens:
            return False

        overlap = question_tokens & previous_tokens
        overlap_ratio = len(overlap) / min(len(question_tokens), len(previous_tokens))
        return overlap_ratio >= 0.6

    def extract_question_tokens(self, question: str) -> set[str]:
        tokens = re.findall(r"[가-힣A-Za-z0-9]+", question.lower())
        return {
            token
            for token in tokens
            if len(token) >= 2 and token not in self.QUESTION_SIMILARITY_STOPWORDS
        }

    def is_unrelated_to_latest_answer(
        self,
        question: str,
        latest_user_message: str,
    ) -> bool:
        if not latest_user_message.strip():
            return False

        user_topics = self.detect_question_topics(latest_user_message)
        if not user_topics:
            return False

        question_topics = self.detect_question_topics(question)
        return bool(question_topics) and user_topics.isdisjoint(question_topics)

    def detect_question_topics(self, text: str) -> set[str]:
        normalized = text.lower()
        return {
            topic
            for topic, keywords in self.QUESTION_TOPIC_KEYWORDS.items()
            if any(keyword.lower() in normalized for keyword in keywords)
        }

    def get_safe_fallback_question(
        self,
        mode: str,
        previous_questions: list[str],
        fallback_questions: tuple[str, ...] | None = None,
        latest_user_message: str = "",
        nickname: str = "사용자",
    ) -> str | None:
        fallback_pool = self.build_contextual_fallback_pool(
            mode=mode,
            nickname=nickname,
            latest_user_message=latest_user_message,
            fallback_questions=fallback_questions,
        )
        valid_fallback_questions = []
        for fallback_question in fallback_pool:
            personalized_question = fallback_question.format(nickname=nickname)
            if self.is_valid_survey_question(
                question=personalized_question,
                mode=mode,
                previous_questions=previous_questions,
            ):
                valid_fallback_questions.append(personalized_question)
                if self.is_repeated_question(
                    question=personalized_question,
                    previous_questions=previous_questions,
                ):
                    continue
                return personalized_question
        return valid_fallback_questions[0] if valid_fallback_questions else None

    def build_contextual_fallback_pool(
        self,
        mode: str,
        nickname: str,
        latest_user_message: str,
        fallback_questions: tuple[str, ...] | None = None,
    ) -> tuple[str, ...]:
        base_pool = fallback_questions or self.get_fallback_question_pool(mode)
        if mode != "NEXT" or not latest_user_message.strip():
            return base_pool

        normalized_message = latest_user_message.lower()
        contextual_question = next(
            (
                question
                for _, keywords, question in self.CONTEXTUAL_NEXT_FALLBACK_RULES
                if any(keyword.lower() in normalized_message for keyword in keywords)
            ),
            (
                "{nickname}님은 혼자 진행하는 방식과 다른 사람과 함께하는 방식 중 "
                "어느 쪽이 더 편한지 말씀해 주세요."
            ),
        )

        return (contextual_question, *base_pool)

    def get_fallback_question_pool(self, mode: str) -> tuple[str, ...]:
        if mode == "NEXT":
            return self.SAFE_NEXT_FALLBACK_QUESTIONS
        if mode == "REASK":
            return self.SAFE_REASK_FALLBACK_QUESTIONS
        if mode == "CLARIFY":
            return self.SAFE_CLARIFY_FALLBACK_QUESTIONS
        return self.SAFE_FALLBACK_QUESTIONS

    # 첫 질문 생성에 사용할 user 프롬프트를 호출
    def load_first_question_prompt(self) -> str:
        return SURVEY_CHATBOT_USER_PROMPT.strip()

    def load_first_question_system_prompt(self) -> str:
        return SURVEY_CHATBOT_SYSTEM_PROMPT.strip()

    def load_first_question_user_prompt(self) -> str:
        return SURVEY_CHATBOT_USER_PROMPT.strip()

    def get_user_nickname(self, user: Any | None) -> str:
        nickname = getattr(user, "nickname", None)
        return str(nickname).strip() if nickname else "사용자"

    # 첫 질문 생성 프롬프트를 그대로 사용해 프롬프트 파일의 계약을 보존
    def build_first_question_prompt(self, user: Any | None = None) -> str:
        return self.load_first_question_prompt().format(
            nickname=self.get_user_nickname(user)
        )

    def build_first_question_prompts(self, user: Any | None = None) -> tuple[str, str]:
        nickname = self.get_user_nickname(user)
        return (
            self.load_first_question_system_prompt().format(nickname=nickname),
            self.load_first_question_user_prompt().format(nickname=nickname),
        )
