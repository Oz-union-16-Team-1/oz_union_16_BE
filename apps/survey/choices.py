from django.db import models


class SurveyStatusChoices(models.TextChoices):
    OPEN = "open", "열림"
    IN_PROGRESS = "in_progress", "진행 중"
    CLOSED = "closed", "종료"


class SurveyRoleChoices(models.TextChoices):
    USER = "user", "사용자"
    AI = "chatbot", "챗봇"
