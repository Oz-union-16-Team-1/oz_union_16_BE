from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser

from apps.core.exceptions import ConflictException

User = get_user_model()


class UserInfoService:
    @staticmethod
    def get_user_info(user: AbstractBaseUser) -> AbstractBaseUser:
        return user

    @staticmethod
    def update_user_profile_nickname(
        user: AbstractBaseUser, data: dict
    ) -> dict[str, str]:
        new_nickname = data.get("nickname")
        if (
            new_nickname
            and User.objects.filter(nickname=new_nickname).exclude(id=user.id).exists()
        ):
            raise ConflictException(
                field="nickname", detail="중복된 닉네임이 존재합니다."
            )

        for attr, value in data.items():
            setattr(user, attr, value)
        user.save()

        return {
            "nickname": user.nickname,
            "profile_img_url": user.profile_img_url,
            "detail": "회원 정보가 수정되었습니다.",
        }
