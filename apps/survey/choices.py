from django.db import models


class SurveyStatusChoices(models.TextChoices):
    OPEN = "open"
    ACTIVATED = "activated"
    CLOSED = "closed"


class SurveyRoleChoices(models.TextChoices):
    USER = "user"
    AI = "chatbot"
