from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from rest_framework.exceptions import (
    AuthenticationFailed,
)

User = get_user_model()


class CheckPwdService:
    @staticmethod
    def check_user_password(user: AbstractBaseUser, password: str) -> None:
        if not user.check_password(password):
            raise AuthenticationFailed(detail="비밀번호가 일치하지 않습니다.")
