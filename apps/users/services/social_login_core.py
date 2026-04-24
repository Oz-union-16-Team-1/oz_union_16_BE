import uuid
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class SocialLoginException(APIException):
    """소셜 provider API 호출 실패 → 502"""
    status_code = 502
    default_detail = "소셜 로그인 처리 중 오류가 발생했습니다."


@dataclass
class SocialUserInfo:
    provider: str
    provider_id: str
    nickname: str


def generate_unique_nickname(base: str) -> str:
    """닉네임 중복 시 uuid suffix를 붙여 유니크하게 생성 (최대 10자)"""
    if not User.objects.filter(nickname=base).exists():
        return base
    for _ in range(20):
        suffix = uuid.uuid4().hex[:4]
        candidate = f"{base[:6]}_{suffix}"
        if not User.objects.filter(nickname=candidate).exists():
            return candidate
    return uuid.uuid4().hex[:10]

def issue_jwt(user) -> dict[str, str]:
    """유저로부터 JWT 토큰 쌍을 발급합니다."""
    refresh = RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    }