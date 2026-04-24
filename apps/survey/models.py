from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.core.models import TimeStampedModel, UUIDModel
from apps.survey.choices import (
    ChatbotModelChoices,
    SurveyRoleChoices,
    SurveyStatusChoices,
)


# 챗봇 세션 모델
class SurveyChatbotSession(TimeStampedModel):
    id = models.UUIDField(
        primary_key=True,
        default=UUIDModel._meta.get_field("id").default,
        editable=False,
        db_column="survey_chatbot_sessions_id",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="survey_chatbot_session",
        verbose_name="사용자",
    )
    using_model = models.CharField(
        max_length=50,
        choices=ChatbotModelChoices.choices,
        db_column="using_model",
        null=True,
        blank=True,
        verbose_name="사용 모델",
    )

    status = models.CharField(
        max_length=11,
        choices=SurveyStatusChoices.choices,
        default=SurveyStatusChoices.OPEN,
        db_column="status",
        verbose_name="세션 상태",
    )
    target_question_count = models.PositiveSmallIntegerField(
        db_column="target_question_count",
        null=True,
        blank=True,
        verbose_name="목표 질문 수",
    )

    class Meta:
        db_table = "survey_chatbot_sessions"
        verbose_name = "챗봇 세션"


# 챗봇 메시지 모델
class SurveyChatbotMessage(TimeStampedModel):
    survey_chatbot_messages_id = models.BigAutoField(
        primary_key=True, db_column="survey_chatbot_messages_id"
    )
    message = models.TextField(
        db_column="message", null=True, verbose_name="메시지 내용"
    )
    role = models.CharField(
        max_length=10,
        choices=SurveyRoleChoices.choices,
        db_column="role",
        null=True,
        verbose_name="발신 주체",
    )
    sequence = models.IntegerField(db_column="sequence", null=True, verbose_name="순서")
    session = models.ForeignKey(
        SurveyChatbotSession,
        on_delete=models.CASCADE,
        db_column="survey_chatbot_sessions_id",
        related_name="messages",
        verbose_name="소속 세션",
    )

    class Meta:
        db_table = "survey_chatbot_messages"
        verbose_name = "챗봇 메시지"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "sequence"],
                name="uq_survey_chatbot_messages_session_sequence",
            )
        ]


# 설문 결과 모델
class SurveyResults(TimeStampedModel):
    survey_results_id = models.BigAutoField(
        primary_key=True, db_column="survey_results_id"
    )
    survey_answer = models.TextField(
        db_column="survey_answer", null=True, blank=True, verbose_name="유저 답변 요약"
    )
    # 직접 언급한 게임명/시리즈명 등 추천 후보에서 제외할 키워드 목록
    excluded_keywords = models.TextField(
        db_column="excluded_keywords",
        null=True,
        blank=True,
        verbose_name="추천 제외 키워드",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="survey_results",
    )
    chatbot_session = models.OneToOneField(
        "SurveyChatbotSession",
        on_delete=models.CASCADE,
        db_column="survey_chatbot_sessions_id",
        related_name="results",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "survey_results"
        verbose_name = "설문 결과"


# 게임 마스터 벡터
class SurveyGameVector(TimeStampedModel):
    survey_game_vector_id = models.BigAutoField(
        primary_key=True, db_column="survey_game_vector_id"
    )
    embedding = VectorField(
        dimensions=1536, db_column="embedding", null=True, blank=True
    )
    game_list = models.BigIntegerField(db_column="game_id", verbose_name="게임 ID")

    class Meta:
        db_table = "survey_game_vector"
        verbose_name = "게임 벡터"
