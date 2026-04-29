from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.exceptions import NotFound

User = get_user_model()
SOCIAL_KEYWORDS = ["naver", "google", "kakao", "admin"]


class UserVerifySocialService:

    @staticmethod
    def check_social_user(user: AbstractBaseUser):
        login_id = (
            getattr(user, "login_id", "") or getattr(user, "username", "")
        ).lower()

        if login_id == "":
            raise NotFound("User not found")

        for keyword in SOCIAL_KEYWORDS:
            if login_id.startswith(keyword):
                return {"is_social": True, "social_type": keyword}

        return {"is_social": False, "social_type": "normal"}
