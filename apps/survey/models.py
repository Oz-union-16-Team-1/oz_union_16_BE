from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.core.models import TimeStampedModel, UUIDModel
from apps.survey.choices import ChatbotModelChoices, SurveyRoleChoices


# 챗봇 세션 모델
class SurveyChatbotSession(UUIDModel, TimeStampedModel):

    using_model = models.CharField(
        max_length=50,
        choices=ChatbotModelChoices.choices,
        db_column="using_model",
        null=True,
        blank=True,
        verbose_name="사용 모델",
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


# 설문 결과 모델
class SurveyResults(TimeStampedModel):
    survey_results_id = models.BigAutoField(
        primary_key=True, db_column="survey_results_id"
    )
    survey_answer = models.TextField(
        db_column="survey_answer", null=True, blank=True, verbose_name="유저 답변 요약"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="survey_results",
    )
    chatbot_session = models.ForeignKey(
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
    embedding = VectorField(dimensions=1536, db_column="embedding", null=True)

    class Meta:
        db_table = "survey_game_vector"
        verbose_name = "게임 벡터"


# 게임 리스트
class SurveyRecommendGameList(TimeStampedModel):
    survey_recommend_game_list_id = models.BigAutoField(
        primary_key=True, db_column="survey_recommend_game_list_id"
    )
    game_id = models.IntegerField(
        db_column="game_id", null=True, verbose_name="IGDB 게임 ID"
    )
    title = models.CharField(max_length=30, db_column="title", null=True)
    genre = models.TextField(db_column="genre", null=True)
    description = models.TextField(db_column="description", null=True)
    cover_url = models.URLField(db_column="cover_url", null=True)

    survey_game_vector = models.ForeignKey(
        SurveyGameVector,
        on_delete=models.CASCADE,
        db_column="survey_game_vector_id",
        related_name="games",
    )

    class Meta:
        db_table = "survey_recommend_game_list"
        verbose_name = "게임 마스터 정보"
