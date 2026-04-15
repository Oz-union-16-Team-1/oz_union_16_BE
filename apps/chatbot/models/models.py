from django.db import models
from django.utils import timezone
from datetime import timedelta


class ChatbotSession(models.Model):
    chatbot_sessions_id = models.BigAutoField(primary_key=True)

    # 세션 생성 시각
    created_at = models.DateTimeField(auto_now_add=True)

    # 세션 만료 시각
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "chatbot_sessions"

    def save(self, *args, **kwargs):
        # expires_at이 없으면 기본 30분 뒤로 설정
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(minutes=30)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at