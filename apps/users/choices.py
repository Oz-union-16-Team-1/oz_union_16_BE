from django.db import models


class GenderChoices(models.TextChoices):
    MALE = "M", "M", "m"
    WOMAN = "W", "W", "w"


class StatusChoices(models.TextChoices):
    ACTIVE = "ACTIVE", "active"
    BLOCKED = "SUSPENDED", "suspended"


class SocialProvider(models.TextChoices):
    KAKAO = "kakao"
    NAVER = "naver"
    GOOGLE = "google"