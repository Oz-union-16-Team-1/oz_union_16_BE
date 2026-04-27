from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.exceptions import AuthenticationFailed

User = get_user_model()


class UserChangePwdService:

    @staticmethod
    def update_password(
        user: AbstractBaseUser, old_password: str, new_password: str
    ) -> None:
        if not user.check_password(old_password):
            raise AuthenticationFailed(detail="현재 비밀번호가 일치하지 않습니다.")

        user.set_password(new_password)
        user.save()
