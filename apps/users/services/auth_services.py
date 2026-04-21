from typing import cast

from django.contrib.auth import authenticate, get_user_model
from rest_framework.exceptions import (
    AuthenticationFailed,
    PermissionDenied,
    ValidationError,
)
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken, Token

from apps.core.exceptions import ConflictException

User = get_user_model()


class AuthService:

    @staticmethod
    def sign_up(validated_data: dict) -> None:

        if len(validated_data["password"]) < 8:
            raise ValidationError("비밀번호는 8자 이상이어야 합니다.")

        if User.objects.filter(login_id=validated_data["login_id"]).exists():
            raise ConflictException(
                field="login_id",
                detail="이미 중복된 회원가입 내역이 존재합니다.",
            )

        if User.objects.filter(nickname=validated_data["nickname"]).exists():
            raise ConflictException(
                field="nickname",
                detail="이미 중복된 닉네임이 존재합니다.",
            )

        validated_data.pop("password_check")
        password = validated_data.pop("password")
        User.objects.create_user(password=password, **validated_data)

    @staticmethod
    def login(login_id: str, password: str) -> dict:
        try:
            user = User.objects.get(login_id=login_id)
        except User.DoesNotExist:
            raise AuthenticationFailed(
                "로그인 아이디 또는 비밀번호가 올바르지 않습니다."
            )

        if not user.check_password(password):
            raise AuthenticationFailed(
                "로그인 아이디 또는 비밀번호가 올바르지 않습니다."
            )

        if not user.is_active:
            raise PermissionDenied("차단된 계정입니다.")

        refresh = RefreshToken.for_user(user)
        return {
            "access_token": str(refresh.access_token),
            "refresh_token": str(refresh),
        }

    @staticmethod
    def logout(refresh_token: str | None) -> None:
        if not refresh_token:
            raise AuthenticationFailed("자격 인증 데이터가 제공되지 않았습니다.")

        try:
            token = RefreshToken(cast(Token, refresh_token))
            token.blacklist()
        except TokenError:
            raise PermissionDenied("인증 정보가 유효하지 않거나 만료되었습니다.")

    @staticmethod
    def refresh(refresh_token: str | None) -> dict:
        if not refresh_token:
            raise AuthenticationFailed("자격 인증 데이터가 제공되지 않았습니다.")

        try:
            old_token = RefreshToken(cast(Token, refresh_token))

            old_token.blacklist()

            user_id = old_token["user_id"]
            user = User.objects.get(pk=user_id)
            new_refresh = RefreshToken.for_user(user)

        except TokenError:
            raise PermissionDenied("인증 정보가 유효하지 않거나 만료되었습니다.")

        except User.DoesNotExist:
            raise AuthenticationFailed("자격 인증 데이터가 제공되지 않았습니다.")

        return {
            "access_token": str(new_refresh.access_token),
            "refresh_token": str(new_refresh),
        }
