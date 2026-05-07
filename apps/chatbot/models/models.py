from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel


class ChatbotSession(TimeStampedModel, UUIDModel):

    # 만료 시각
    expires_at = models.DateTimeField()
    pending_question = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "chatbot_sessions"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class ChatbotMessage(TimeStampedModel, UUIDModel):
    class Role(models.TextChoices):
        USER = "user", "user"
        ASSISTANT = "assistant", "assistant"

    session = models.ForeignKey(
        ChatbotSession,
        related_name="messages",
        on_delete=models.CASCADE,
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField()

    class Meta:
        db_table = "chatbot_session_messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]
