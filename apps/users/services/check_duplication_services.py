from django.contrib.auth import get_user_model

from apps.core.exceptions import ConflictException

User = get_user_model()


class CheckService:
    @staticmethod
    def check_id(check_login_id: str) -> str:
        if User.objects.filter(login_id=check_login_id).exists():
            raise ConflictException(
                field="login_id", detail="중복된 아이디가 존재합니다."
            )
        return "사용가능한 아이디 입니다."

    @staticmethod
    def check_nickname(check_nickname: str) -> str:
        if User.objects.filter(nickname=check_nickname).exists():
            raise ConflictException(
                field="nickname", detail="중복된 닉네임이 존재합니다."
            )
        return "사용가능한 닉네임 입니다."
