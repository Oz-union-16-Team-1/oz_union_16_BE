from django.db import models
from django.db.models import Q, Max


class ChatbotSession(models.Model):
    chatbot_sessions_id = models.BigAutoField(primary_key=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chatbot_sessions"


class ChatbotMessage(models.Model):
    class RoleChoices(models.TextChoices):
        USER = "USER", "USER"
        ASSISTANT = "ASSISTANT", "ASSISTANT"

    chatbot_completions_id = models.BigAutoField(primary_key=True)

    role = models.CharField(max_length=10, choices=RoleChoices.choices)

    sequence = models.PositiveIntegerField()

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    chatbot_session = models.ForeignKey(
        ChatbotSession,
        on_delete=models.CASCADE,
        db_column="chatbot_sessions_id",
        related_name="messages",
    )

    # 🔥 자동 sequence 처리
    def save(self, *args, **kwargs):
        if not self.sequence:
            last = ChatbotMessage.objects.filter(
                chatbot_session=self.chatbot_session
            ).aggregate(max_seq=Max("sequence"))["max_seq"]

            self.sequence = (last or 0) + 1

        super().save(*args, **kwargs)

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
