import uuid

from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.core.models import TimeStampedModel
from apps.survey.choices import SurveyRoleChoices, SurveyStatusChoices


# 1. 설문/대화 세션 모델
class SurveyChatbotSession(TimeStampedModel):
    """
    사용자와 AI 간의 추천 설문 세션을 관리하는 모델입니다.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chatbot_sessions",
        verbose_name="사용자",
    )
    status = models.CharField(
        max_length=20,
        choices=SurveyStatusChoices.choices,
        default=SurveyStatusChoices.OPEN,
        verbose_name="세션 상태",
    )

    # 33%, 66%, 100% 등 퍼센트 단위로 진행률 표시
    progress_rate = models.CharField(max_length=4, default="0%", verbose_name="진행률")

    summary_text = models.TextField(
        null=True,
        blank=True,
        help_text="LLM이 대화 종료 후 요약한 유저의 취향 문장",
        verbose_name="취향 요약",
    )

    class Meta:
        db_table = "chatbot_sessions"
        verbose_name = "챗봇 세션"
        verbose_name_plural = "챗봇 세션 목록"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.status} ({self.progress_rate})"


# 2. 대화 메시지 이력 모델
class ChatbotMessage(TimeStampedModel):
    """
    세션 내에서 발생하는 개별 대화 메시지를 저장하는 모델입니다.
    """

    session = models.ForeignKey(
        SurveyChatbotSession,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="세션",
    )
    role = models.CharField(
        max_length=10, choices=SurveyRoleChoices.choices, verbose_name="발신 주체"
    )
    content = models.TextField(verbose_name="내용")

    class Meta:
        db_table = "chatbot_messages"
        verbose_name = "챗봇 메시지"
        verbose_name_plural = "챗봇 메시지 목록"
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.session.id}] {self.role}: {self.content[:20]}"


# 3. 유저 취향 벡터 모델
class SurveyPreference(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="survey_preference",  # 역참조 이름 변경 (중요!)
    )

    # OpenAI text-embedding-3-small 모델 기준 1536차원 설정
    survey_vector = VectorField(dimensions=1536, null=True, blank=True)
    match_vector = VectorField(null=True, blank=True)

    # 설문 답변 기록 보관용 필드 (JSON 형식)
    survey_results = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "survey_preferences"


# 4. 게임 마스터 데이터 모델 (추천용 캐시)
class GameCache(models.Model):
    id = models.BigIntegerField(primary_key=True, help_text="IGDB 고유 ID")
    title = models.CharField(max_length=255)
    genres = models.JSONField(default=list, help_text="장르 리스트")
    description = models.TextField()
    cover_url = models.URLField(max_length=500, null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    embedding = VectorField(dimensions=1536)

    class Meta:
        db_table = "game_cache"
