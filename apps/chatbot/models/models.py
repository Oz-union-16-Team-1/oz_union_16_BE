from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel


class ChatbotSession(TimeStampedModel, UUIDModel):

    # 만료 시각
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "chatbot_sessions"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
