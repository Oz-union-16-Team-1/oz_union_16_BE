import uuid

from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.core.models import TimeStampedModel, UUIDModel
from apps.survey.choices import SurveyRoleChoices, SurveyStatusChoices


# 1. 설문/대화 세션 모델
class SurveyChatbotSession(UUIDModel, TimeStampedModel):
    """
    사용자와 AI 간의 추천 설문 세션을 관리하는 모델입니다.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="chatbot_sessions",
        verbose_name="사용자",
    )
    status = models.CharField(
        max_length=10,
        choices=SurveyStatusChoices.choices,
        default=SurveyStatusChoices.OPEN,
        verbose_name="세션 상태",
    )
    progress_rate = models.CharField(max_length=4, default="0%", verbose_name="진행률")
    summary_text = models.TextField(null=True, blank=True, verbose_name="취향 요약")

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


from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.core.models import TimeStampedModel


class SurveyPreference(TimeStampedModel):
    id = models.BigAutoField(
        primary_key=True, db_column="survey_results_id", verbose_name="설문 결과 ID"
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="survey_preference",
        verbose_name="사용자",
    )

    # OpenAI 임베딩 모델(1536차원) 결과값 저장 필드
    survey_vector = VectorField(
        dimensions=1536, null=True, blank=True, verbose_name="취향 벡터"
    )

    # JSON 파싱 없이 대화 요약본을 직접 저장하는 필드
    raw_preference_text = models.TextField(
        null=True,
        blank=True,
        verbose_name="원본 취향 텍스트",
        help_text="LLM이 요약한 자연어 취향 문장을 저장하며, 벡터 생성의 소스로 사용됩니다.",
    )

    class Meta:
        # ERD에 명시된 테이블명 준수
        db_table = "survey_results"
        verbose_name = "설문 결과 및 취향"
        verbose_name_plural = "설문 결과 및 취향 목록"

    def __str__(self):
        return f"{self.user} - Preference Profile"


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
