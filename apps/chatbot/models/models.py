from datetime import timedelta

from django.db import models
from django.utils import timezone


class ChatbotSession(models.Model):
    class SessionTypeChoices(models.TextChoices):
        CHATBOT = "CHATBOT", "챗봇"
        SURVEY = "SURVEY", "설문"

    chatbot_sessions_id = models.BigAutoField(primary_key=True)

    # 세션 타입 추가
    session_type = models.CharField(
        max_length=20,
        choices=SessionTypeChoices.choices,
        default=SessionTypeChoices.CHATBOT,
    )

    # 생성 시각
    created_at = models.DateTimeField(auto_now_add=True)

    # 만료 시각
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "chatbot_sessions"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
