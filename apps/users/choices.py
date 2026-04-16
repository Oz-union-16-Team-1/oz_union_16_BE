from django.db import models


class GenderChoices(models.TextChoices):
    MALE = "M", "M"
    WOMAN = "W", "W"


class StatusChoices(models.TextChoices):
    ACTIVE = "ACTIVE", "active"
    SUSPENDED = "SUSPENDED", "suspended"


class SocialProvider(models.TextChoices):
    KAKAO = "kakao"
    NAVER = "naver"
    GOOGLE = "google"
