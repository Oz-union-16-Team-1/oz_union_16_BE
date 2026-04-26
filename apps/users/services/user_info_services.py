from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AbstractBaseUser

User = get_user_model()


class UserInfoService:
    @staticmethod
    def get_user_info(user: AbstractBaseUser) -> AbstractBaseUser:
        return user
