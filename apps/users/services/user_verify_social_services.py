from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.exceptions import NotFound

from apps.users.models import SocialUser

User = get_user_model()


class UserVerifySocialService:

    @staticmethod
    def check_social_user(user: AbstractBaseUser):
        if not user.pk:
            raise NotFound("User not found")

        if getattr(user, "is_staff", False):
            return {"is_social": True, "social_type": "admin"}

        social = SocialUser.objects.filter(user=user).first()
        if social:
            return {"is_social": True, "social_type": social.provider}

        return {"is_social": False, "social_type": "normal"}
