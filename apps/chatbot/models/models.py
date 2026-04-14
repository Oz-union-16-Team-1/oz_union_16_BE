from django.db import models
from django.db.models import Q


class ChatbotSession(models.Model):
    chatbot_sessions_id = models.BigAutoField(primary_key=True)

    # 현재 화면에서만 사용하는 임시 세션 식별자
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 임시 세션 만료 시각
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chatbot_sessions"


class ChatbotMessage(models.Model):
    class RoleChoices(models.TextChoices):
        USER = "USER", "USER"
        ASSISTANT = "ASSISTANT", "ASSISTANT"

    chatbot_completions_id = models.BigAutoField(primary_key=True)

    # 사용자 / 챗봇 메시지 구분
    role = models.CharField(max_length=10, choices=RoleChoices.choices)

    # 세션 내 메시지 순서
    sequence = models.PositiveIntegerField()

    # 실제 대화 내용
    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    # 한 세션에 여러 메시지 (1:N)
    chatbot_session = models.ForeignKey(
        ChatbotSession,
        on_delete=models.CASCADE,
        db_column="chatbot_sessions_id",
        related_name="messages",
    )

    class Meta:
        db_table = "chatbot_messages"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["chatbot_session", "sequence"],
                name="uq_chatbot_messages_session_sequence",
            ),
            models.CheckConstraint(
                condition=Q(sequence__gte=1),
                name="ck_chatbot_messages_sequence_positive",
            ),
            models.CheckConstraint(
                condition=~Q(message=""),
                name="ck_chatbot_messages_not_empty",
            ),
        ]
