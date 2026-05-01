import urllib.parse
import uuid
from abc import ABC, abstractmethod
from typing import Any, cast

import requests
from django.conf import settings

from apps.users.choices import SocialProvider
from apps.users.models import SocialUser
from apps.users.services.social_login_core import (
    SocialLoginException,
    generate_unique_nickname,
    issue_jwt,
)

# ---------------------------------------------------------------------------
# Base OAuth Service
# ---------------------------------------------------------------------------


class BaseOAuthService(ABC):
    """공통 OAuth 흐름을 처리하는 추상 베이스 클래스."""

    AUTH_URL: str
    TOKEN_URL: str
    USER_INFO_URL: str
    PROVIDER: str

    # -- 인증 URL --

    def get_auth_url(self, is_local: bool = False) -> str:
        """인증 페이지 URL 반환. is_local=True 시 로컬 redirect_uri 사용."""
        params = {
            **self._base_auth_params(is_local),
            "response_type": "code",
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"

    @abstractmethod
    def _base_auth_params(self, is_local: bool) -> dict[str, str]:
        """provider별 인증 파라미터 반환 (client_id, redirect_uri 등)."""

    def get_access_token(self, code: str, **kwargs: Any) -> str:
        res = requests.post(
            self.TOKEN_URL,
            data=self._token_data(code, **kwargs),
            timeout=10,
        )
        if not res.ok:
            raise SocialLoginException(f"{self.PROVIDER} 토큰 발급에 실패했습니다.")
        return cast(str, res.json()["access_token"])

    @abstractmethod
    def _token_data(self, code: str, **kwargs: Any) -> dict[str, str]:
        """provider별 토큰 요청 파라미터 반환."""

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        res = requests.get(
            self.USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if not res.ok:
            raise SocialLoginException(
                f"{self.PROVIDER} 유저 정보 조회에 실패했습니다."
            )
        return cast(dict[str, Any], self._parse_user_info(res.json()))

    def _parse_user_info(self, raw: dict[str, Any]) -> dict[str, Any]:
        """응답 JSON을 표준 형태로 가공. 필요한 provider만 오버라이드."""
        return raw

    def get_or_create_user(self, user_info: dict[str, Any]) -> Any:
        from django.contrib.auth import get_user_model

        UserModel = get_user_model()

        provider_id, nickname, name = self._extract_user_info(user_info)

        social_user = (
            SocialUser.objects.filter(provider=self.PROVIDER, provider_id=provider_id)
            .select_related("user")
            .first()
        )
        if social_user:
            return social_user.user

        unique_nickname = generate_unique_nickname(nickname[:10])
        user = UserModel.objects.create_user(
            login_id=f"{self.PROVIDER}_{uuid.uuid4().hex[:10]}",
            name=name[:30],
            nickname=unique_nickname,
            gender="M",
        )
        SocialUser.objects.create(
            provider=self.PROVIDER,
            provider_id=provider_id,
            user=user,
        )
        return user

    @abstractmethod
    def _extract_user_info(self, user_info: dict[str, Any]) -> tuple[str, str, str]:
        """(provider_id, nickname, name) 튜플 반환."""

    def login(self, code: str, **kwargs: Any) -> dict[str, str]:
        access_token = self.get_access_token(code, **kwargs)
        user_info = self.get_user_info(access_token)
        user = self.get_or_create_user(user_info)
        return issue_jwt(user)


# ---------------------------------------------------------------------------
# Kakao
# ---------------------------------------------------------------------------


class KakaoOAuthService(BaseOAuthService):
    AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"
    PROVIDER = SocialProvider.KAKAO

    def _base_auth_params(self, is_local: bool) -> dict[str, str]:
        redirect_uri = (
            settings.KAKAO_LOCAL_REDIRECT_URI
            if is_local
            else settings.KAKAO_REDIRECT_URI
        )
        return {
            "client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": redirect_uri,
        }

    def _token_data(self, code: str, **kwargs: Any) -> dict[str, str]:
        is_local: bool = kwargs.get("is_local", False)
        redirect_uri = (
            settings.KAKAO_LOCAL_REDIRECT_URI
            if is_local
            else settings.KAKAO_REDIRECT_URI
        )
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        if settings.KAKAO_CLIENT_SECRET:
            data["client_secret"] = settings.KAKAO_CLIENT_SECRET
        return data

    def _extract_user_info(self, user_info: dict[str, Any]) -> tuple[str, str, str]:
        kakao_id = str(user_info["id"])
        profile = user_info.get("kakao_account", {}).get("profile", {})
        nickname = profile.get("nickname") or f"kakao_{kakao_id[:4]}"
        return kakao_id, nickname, nickname


# ---------------------------------------------------------------------------
# Naver
# ---------------------------------------------------------------------------


class NaverOAuthService(BaseOAuthService):
    AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"
    TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
    USER_INFO_URL = "https://openapi.naver.com/v1/nid/me"
    PROVIDER = SocialProvider.NAVER

    def get_auth_url(self, is_local: bool = False) -> tuple[str, str]:  # type: ignore[override]
        """네이버는 CSRF 방어를 위해 state를 함께 반환합니다."""
        state = uuid.uuid4().hex
        params = {
            **self._base_auth_params(is_local),
            "response_type": "code",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}", state

    def _base_auth_params(self, is_local: bool) -> dict[str, str]:
        redirect_uri = (
            settings.NAVER_LOCAL_REDIRECT_URI
            if is_local
            else settings.NAVER_REDIRECT_URI
        )
        return {
            "client_id": settings.NAVER_CLIENT_ID,
            "redirect_uri": redirect_uri,
        }

    def _token_data(self, code: str, **kwargs: Any) -> dict[str, str]:
        return {
            "grant_type": "authorization_code",
            "client_id": settings.NAVER_CLIENT_ID,
            "client_secret": settings.NAVER_CLIENT_SECRET,
            "code": code,
            "state": kwargs["state"],
        }

    def _parse_user_info(self, raw: dict[str, Any]) -> dict[str, Any]:
        profile = raw.get("response")
        if not profile:
            raise SocialLoginException("네이버 프로필 응답이 비어있습니다.")
        return cast(dict[str, Any], profile)

    def _extract_user_info(self, user_info: dict[str, Any]) -> tuple[str, str, str]:
        naver_id = str(user_info["id"])
        nickname = user_info.get("nickname") or f"naver_{naver_id[:4]}"
        name = user_info.get("name") or nickname
        return naver_id, nickname, name


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


class GoogleOAuthService(BaseOAuthService):
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    PROVIDER = SocialProvider.GOOGLE

    def _base_auth_params(self, is_local: bool) -> dict[str, str]:
        redirect_uri = (
            settings.GOOGLE_LOCAL_REDIRECT_URI
            if is_local
            else settings.GOOGLE_REDIRECT_URI
        )
        return {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
        }

    def _token_data(self, code: str, **kwargs: Any) -> dict[str, str]:
        is_local: bool = kwargs.get("is_local", False)
        redirect_uri = (
            settings.GOOGLE_LOCAL_REDIRECT_URI
            if is_local
            else settings.GOOGLE_REDIRECT_URI
        )
        return {
            "grant_type": "authorization_code",
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "code": code,
        }

    def _extract_user_info(self, user_info: dict[str, Any]) -> tuple[str, str, str]:
        google_id = str(user_info["id"])
        nickname = user_info.get("name") or f"google_{google_id[:4]}"
        return google_id, nickname, nickname
