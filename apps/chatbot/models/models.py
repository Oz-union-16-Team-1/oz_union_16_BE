from django.db import models
from django.db.models import Q


class ChatbotSession(models.Model):
    class UsingModelChoices(models.TextChoices):
        GEMINI_2_5 = (
            "GEMINI_2.5",
            "Gemini 2.5",
        )  # 첫번쨰: DB 저장되는 실제값(value), 두번째: 화면/admin에서 보여주는 라벨(label)

    class StatusChoices(models.TextChoices):
        ACTIVE = "ACTIVE", "ACTIVE"
        CLOSED = "CLOSED", "CLOSED"
        EXPIRED = "EXPIRED", "EXPIRED"

    chatbot_sessions_id = models.BigAutoField(primary_key=True)
    using_model = models.CharField(max_length=30, choices=UsingModelChoices.choices)

    # 세션 라이프사이클 상태
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "chatbot_sessions"


class ChatbotMessage(models.Model):
    class RoleChoices(models.TextChoices):
        USER = "USER", "USER"
        ASSISTANT = "ASSISTANT", "ASSISTANT"
        SYSTEM = "SYSTEM", "SYSTEM"

    chatbot_completions_id = models.BigAutoField(primary_key=True)

    # 메시지 발화 주체(USER/ASSISTANT/SYSTEM) 구분용
    # 대화 재구성 및 프롬프트 후처리에 사용함
    role = models.CharField(max_length=10, choices=RoleChoices.choices)

    # 세션 내 메시지 순서를 고정하기 위한 번호
    # created_at이 같은 값으로 저장되는 경우에도 안정적인 정렬을 보장함
    sequence = models.IntegerField()

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 한 세션에 여러 메시지 (1:N)
    chatbot_session = models.ForeignKey(
        ChatbotSession,
        on_delete=models.CASCADE,
        db_column="chatbot_sessions_id",
        related_name="messages",
    )

    class Meta:
        db_table = "chatbot_messages"
        constraints = [
            models.UniqueConstraint(  # 세션 내 메시지 순서는 유일해야 함
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
