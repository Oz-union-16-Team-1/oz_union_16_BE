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
    SAFE_FALLBACK_QUESTIONS = (
        "{nickname}님은 최근 가장 오래 플레이했던 게임에서 어떤 재미 때문에 계속 하게 되었는지 말씀해 주세요.",
        "{nickname}님은 최근 몰입해서 플레이했던 게임에서는 어떤 플레이 과정이 가장 기억에 남았는지 말씀해 주세요.",
        "{nickname}님은 혼자 몰입하는 플레이와 다른 사람과 협력하거나 경쟁하는 플레이 중 어떤 경험이 더 잘 맞는지 말씀해 주세요.",
    )
    SAFE_NEXT_FALLBACK_QUESTIONS = (
        "{nickname}님이 방금 말한 경험에서 가장 결정적이었던 행동이나 판단이 무엇이었는지 말씀해 주세요.",
        "{nickname}님은 비슷한 상황에서 빠르게 판단해 움직이는 플레이와 충분히 준비한 뒤 안정적으로 진행하는 플레이 중 어느 쪽이 더 잘 맞나요?",
        "{nickname}님은 게임에서 실력이 늘어 이기는 성취감과 새로운 지역이나 보상을 발견하는 만족감 중 어느 쪽이 더 크게 느껴지나요?",
    )
    SAFE_REASK_FALLBACK_QUESTIONS = (
        "{nickname}님이 최근 플레이한 게임 중 오래 기억나는 장면이 있다면 무엇이 재미있었는지 말씀해 주세요.",
        "{nickname}님은 게임할 때 빠르게 몰아치는 진행과 천천히 준비하며 진행하는 방식 중 어느 쪽이 더 편한지 알려주세요.",
    )
    SAFE_CLARIFY_FALLBACK_QUESTIONS = (
        "쉽게 말해, {nickname}님은 게임을 할 때 전투, 성장, 탐험, 협동 중 무엇이 가장 재미있는지 말씀해 주세요.",
        "질문을 바꿔서 물어볼게요. {nickname}님이 최근 재미있게 한 게임에서 계속 하게 만든 이유를 알려주세요.",
    )
    CONTEXTUAL_NEXT_FALLBACK_RULES = (
        (
            "슈팅",
            ("슈팅", "fps", "에임", "총", "교전", "사이트", "스파이크", "에이스"),
            "{nickname}님이 팀 전략이 성공했던 장면에서 직접 맡은 역할은 진입을 여는 쪽이었는지, 정보를 보고 판단해 마무리하는 쪽이었는지 말씀해 주세요.",
        ),
        (
            "전술",
            ("전술", "전략", "팀", "역할", "포지션", "진입", "수비", "공격"),
            "{nickname}님이 전략이 성공했던 장면에서 더 중요했던 건 맡은 역할을 정확히 수행한 점인지, 상황에 맞춰 판단을 바꾼 점인지 말씀해 주세요.",
        ),
        (
            "모바(MOBA)",
            ("moba", "모바", "라인", "한타", "갱", "오브젝트", "로밍"),
            "{nickname}님이 팀 싸움에서 만족감을 느꼈던 장면은 교전을 여는 역할이었는지, 흐름을 보고 합류해 마무리하는 역할이었는지 말씀해 주세요.",
        ),
        (
            "실시간 전략",
            ("rts", "실시간 전략", "빌드오더", "멀티태스킹", "자원", "유닛"),
            "{nickname}님이 실시간으로 운영했던 장면에서 더 만족스러웠던 건 빠른 자원 관리였는지, 상대 움직임에 맞춘 병력 운용이었는지 말씀해 주세요.",
        ),
        (
            "턴제 전략",
            ("턴제", "tbs", "턴", "수읽기", "행동력", "배치"),
            "{nickname}님이 턴마다 선택을 고민했던 장면에서 더 재미있었던 건 안전한 계산이었는지, 위험을 감수한 큰 수였는지 말씀해 주세요.",
        ),
        (
            "전략",
            ("전략", "운영", "계획", "판단", "상황 판단", "전술"),
            "{nickname}님이 전략적으로 성공했던 장면에서 더 만족스러웠던 건 미리 세운 계획이 맞아떨어진 순간인지, 예상 밖 상황에 맞춰 운영을 바꾼 순간인지 말씀해 주세요.",
        ),
        (
            "격투",
            ("격투", "콤보", "심리전", "반격", "카운터", "잡기"),
            "{nickname}님이 상대를 이겼던 장면에서 더 짜릿했던 건 상대 패턴을 읽고 반격한 순간인지, 연습한 콤보를 정확히 성공시킨 순간인지 말씀해 주세요.",
        ),
        (
            "액션",
            ("액션", "회피", "공격", "타격", "전투", "손맛", "피지컬"),
            "{nickname}님이 액션 플레이에서 만족했던 장면은 빠르게 반응해 위기를 넘긴 순간인지, 공격 흐름을 직접 만들며 밀어붙인 순간인지 말씀해 주세요.",
        ),
        (
            "핵 앤 슬래시",
            ("핵앤슬래시", "핵 앤 슬래시", "쓸어버", "몰이", "파밍", "스킬 빌드"),
            "{nickname}님이 적을 몰아 상대했던 장면에서 더 재미있었던 건 강한 스킬로 몰아치는 쾌감인지, 장비와 빌드를 맞춰 효율을 높인 과정인지 말씀해 주세요.",
        ),
        (
            "RPG",
            ("rpg", "역할수행", "성장", "레벨", "장비", "빌드", "보스", "퀘스트"),
            "{nickname}님이 캐릭터를 성장시켰던 장면에서 더 만족스러웠던 건 어려운 적을 공략한 순간인지, 장비와 빌드를 준비해 강해지는 과정인지 말씀해 주세요.",
        ),
        (
            "어드벤처",
            ("어드벤처", "탐험", "발견", "단서", "지역", "모험"),
            "{nickname}님이 탐험에서 만족감을 느낀 장면은 숨겨진 장소를 직접 발견한 순간이었는지, 새로운 단서를 따라 세계를 이해한 순간이었는지 말씀해 주세요.",
        ),
        (
            "포인트 앤 클릭",
            ("포인트", "클릭", "단서", "조사", "추리", "상호작용"),
            "{nickname}님이 단서를 찾아 해결했던 장면에서 더 재미있었던 건 사물을 꼼꼼히 조사하는 과정인지, 연결된 단서를 추리해 답을 찾는 과정인지 말씀해 주세요.",
        ),
        (
            "퍼즐",
            ("퍼즐", "규칙", "문제", "논리", "해답", "두뇌"),
            "{nickname}님이 퍼즐을 풀었던 장면에서 더 만족스러웠던 건 규칙을 파악하는 과정인지, 막혔던 해답을 떠올려 해결한 순간인지 말씀해 주세요.",
        ),
        (
            "퀴즈/상식",
            ("퀴즈", "상식", "문제 맞히", "정답", "지식"),
            "{nickname}님이 문제를 맞혔던 장면에서 더 재미있었던 건 알고 있던 지식을 바로 떠올린 순간인지, 힌트를 보고 추론해 맞힌 순간인지 말씀해 주세요.",
        ),
        (
            "시뮬레이션",
            ("시뮬", "시뮬레이션", "관리", "운영", "효율", "루틴"),
            "{nickname}님이 시뮬레이션에서 만족했던 장면은 시스템을 효율적으로 관리한 순간인지, 직접 세운 루틴이 안정적으로 돌아간 순간인지 말씀해 주세요.",
        ),
        (
            "스포츠",
            ("스포츠", "경기", "선수", "팀 운영", "시합", "득점"),
            "{nickname}님이 경기에서 만족감을 느낀 장면은 직접 조작으로 득점한 순간인지, 팀 운영과 전술 선택이 결과로 이어진 순간인지 말씀해 주세요.",
        ),
        (
            "레이싱",
            ("레이싱", "주행", "코스", "기록", "드리프트", "속도"),
            "{nickname}님이 주행에서 만족했던 장면은 코스를 완벽하게 익혀 기록을 줄인 순간인지, 순간적인 조작으로 위기를 넘긴 순간인지 말씀해 주세요.",
        ),
        (
            "플랫폼",
            ("플랫폼", "점프", "타이밍", "발판", "조작", "구간"),
            "{nickname}님이 어려운 구간을 넘겼던 장면에서 더 재미있었던 건 정확한 점프 타이밍인지, 반복 연습으로 조작을 익혀 돌파한 과정인지 말씀해 주세요.",
        ),
        (
            "음악",
            ("음악", "리듬", "박자", "노트", "정확도", "연주"),
            "{nickname}님이 리듬을 맞췄던 장면에서 더 만족스러웠던 건 박자를 정확히 따라간 순간인지, 어려운 구간을 반복 연습해 성공한 순간인지 말씀해 주세요.",
        ),
        (
            "핀볼",
            ("핀볼", "공", "플리퍼", "점수", "반사"),
            "{nickname}님이 점수를 올렸던 장면에서 더 재미있었던 건 공의 흐름을 예측해 조작한 순간인지, 우연한 연쇄 반응이 크게 이어진 순간인지 말씀해 주세요.",
        ),
        (
            "아케이드",
            ("아케이드", "점수", "콤보", "라운드", "짧게", "반복"),
            "{nickname}님이 짧은 판을 반복했던 장면에서 더 끌렸던 건 점수를 조금씩 높이는 과정인지, 즉각적인 조작과 반응으로 결과가 나는 순간인지 말씀해 주세요.",
        ),
        (
            "인디",
            ("인디", "독특", "실험적", "개성", "소규모"),
            "{nickname}님이 인디 게임에서 끌렸던 장면은 익숙하지 않은 규칙을 발견한 순간인지, 독특한 분위기나 표현 방식에 몰입한 순간인지 말씀해 주세요.",
        ),
        (
            "비주얼 노벨",
            ("비주얼노벨", "비주얼 노벨", "선택지", "캐릭터 관계", "분기", "감정선"),
            "{nickname}님이 이야기 선택에서 몰입했던 장면은 캐릭터 관계가 바뀌는 순간인지, 선택에 따라 다른 결말을 확인하는 과정인지 말씀해 주세요.",
        ),
        (
            "카드 및 보드 게임",
            ("카드", "보드", "덱", "수읽기", "패", "카드 조합"),
            "{nickname}님이 카드나 보드 게임에서 만족했던 장면은 덱이나 조합을 미리 준비한 과정인지, 상대 선택을 읽고 대응한 순간인지 말씀해 주세요.",
        ),
    )
    QUESTION_ENDINGS = (
        "?",
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
    FIRST_QUESTION_ENDINGS = (
        "있나요?",
        "주세요.",
        "말씀해 주세요.",
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
    VAGUE_QUESTION_PATTERNS = (
        r"어떤\s*점",
        r"어떤\s*부분",
        r"어떤\s*요소",
        r"어떤\s*경험",
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
                "Empty Gemini response for survey question: %s", response_data
            )
        return question

    # LLM 호출은 1회만 수행하고, 후처리로 보정한 뒤 실패 시 fallback으로 진행
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
        question = self.generate_question_with_llm(
            prompt,
            temperature=temperature,
            system_prompt=system_prompt,
        )
        question = self.normalize_generated_question(question)
        question = self.ensure_nickname_in_question(question, nickname)
        question = self.repair_yes_no_question(question)
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
        if not question:
            return None

        replacements = {
            "좋아하시나요?": "좋아하는 이유나 기억나는 장면을 말씀해 주세요.",
            "좋아하시나요": "좋아하는 이유나 기억나는 장면을 말씀해 주세요.",
            "선호하시나요?": "선호하는 이유나 기억나는 장면을 말씀해 주세요.",
            "선호하시나요": "선호하는 이유나 기억나는 장면을 말씀해 주세요.",
            "즐거우신가요?": "즐거웠던 이유나 기억나는 장면을 말씀해 주세요.",
            "즐거우신가요": "즐거웠던 이유나 기억나는 장면을 말씀해 주세요.",
            "느끼시나요?": "느끼는 이유나 기억나는 장면을 말씀해 주세요.",
            "느끼시나요": "느끼는 이유나 기억나는 장면을 말씀해 주세요.",
        }
        for ending, replacement in replacements.items():
            if question.endswith(ending):
                return f"{question[: -len(ending)].rstrip()} {replacement}"
        return question

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
        return 30 <= len(question) <= 180 and question.endswith(
            self.FIRST_QUESTION_ENDINGS
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

        question = question.strip()
        return 20 <= len(question) <= 180 and question.endswith(self.QUESTION_ENDINGS)

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
        for fallback_question in fallback_pool:
            personalized_question = fallback_question.format(nickname=nickname)
            if self.is_valid_survey_question(
                question=personalized_question,
                mode=mode,
                previous_questions=previous_questions,
            ):
                return personalized_question
        return fallback_pool[0].format(nickname=nickname) if fallback_pool else None

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
                "{nickname}님이 방금 말한 경험에서 가장 결정적이었던 행동이나 "
                "판단이 무엇이었는지 말씀해 주세요."
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
