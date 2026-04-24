import urllib.parse
from typing import Any, cast

import requests
from django.conf import settings

from apps.users.choices import SocialProvider
from apps.users.models import SocialUser

from apps.users.services.social_login_core import *


# ---------------------------------------------------------------------------
# Provider 클라이언트
# ---------------------------------------------------------------------------

class KakaoOAuthService:
    AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"

    def get_auth_url(self) -> str:
        """카카오 인증 페이지 URL 반환"""
        params = {
            "client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": settings.KAKAO_REDIRECT_URI,
            "response_type": "code",
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"

    def get_local_auth_url(self) -> str:
        """카카오 인증 페이지 URL 반환"""
        params = {
            "client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": settings.KAKAO_LOCAL_REDIRECT_URI,
            "response_type": "code",
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"

    def get_access_token(self, code: str) -> str:
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": settings.KAKAO_REDIRECT_URI,
            "code": code,
        }
        if settings.KAKAO_CLIENT_SECRET:
            data["client_secret"] = settings.KAKAO_CLIENT_SECRET

        res = requests.post(self.TOKEN_URL, data=data, timeout=10)
        if not res.ok:
            raise SocialLoginException("카카오 토큰 발급에 실패했습니다.")
        return cast(str, res.json()["access_token"])

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        res = requests.get(
            self.USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if not res.ok:
            raise SocialLoginException("카카오 유저 정보 조회에 실패했습니다.")
        return cast(dict[str, Any], res.json())

    def get_or_create_user(self, user_info: dict[str, Any]) -> Any:
        kakao_id = str(user_info["id"])
        profile = user_info.get("kakao_account", {}).get("profile", {})
        nickname = profile.get("nickname") or f"kakao_{kakao_id[:4]}"

        social_user = (
            SocialUser.objects
            .filter(provider=SocialProvider.KAKAO, provider_id=kakao_id)
            .select_related("user")
            .first()
        )
        if social_user:
            return social_user.user

        unique_nickname = generate_unique_nickname(nickname[:10])
        user = User.objects.create_user(
            login_id=f"kakao_{uuid.uuid4().hex[:10]}",
            name=nickname[:30],
            nickname=unique_nickname,
            gender="M",
            password=None,
        )
        SocialUser.objects.create(
            provider=SocialProvider.KAKAO,
            provider_id=kakao_id,
            user=user,
        )
        return user

    def login(self, code: str) -> dict[str, str]:
        """code → 유저 조회/생성 → JWT 발급까지 처리"""
        access_token = self.get_access_token(code)
        user_info = self.get_user_info(access_token)
        user = self.get_or_create_user(user_info)
        return issue_jwt(user)


class NaverOAuthService:
    AUTH_URL = "https://nid.naver.com/oauth2.0/authorize"
    TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
    USER_INFO_URL = "https://openapi.naver.com/v1/nid/me"

    def get_auth_url(self) -> tuple[str, str]:
        """
        네이버 인증 페이지 URL과 state를 함께 반환합니다.
        state는 CSRF 방어용으로 콜백에서 검증에 사용됩니다.
        """
        state = uuid.uuid4().hex
        params = {
            "client_id": settings.NAVER_CLIENT_ID,
        "redirect_uri": settings.NAVER_REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}", state

    def get_local_auth_url(self) -> tuple[str, str]:
        """
        네이버 인증 페이지 URL과 state를 함께 반환합니다.
        state는 CSRF 방어용으로 콜백에서 검증에 사용됩니다.
        """
        state = uuid.uuid4().hex
        params = {
            "client_id": settings.NAVER_CLIENT_ID,
            "redirect_uri": settings.NAVER_LOCAL_REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}", state

    def get_access_token(self, code: str, state: str) -> str:
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.NAVER_CLIENT_ID,
            "client_secret": settings.NAVER_CLIENT_SECRET,
            "code": code,
            "state": state,
        }
        res = requests.post(self.TOKEN_URL, data=data, timeout=10)
        if not res.ok:
            raise SocialLoginException("네이버 토큰 발급에 실패했습니다.")
        return cast(str, res.json()["access_token"])

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        res = requests.get(
            self.USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if not res.ok:
            raise SocialLoginException("네이버 유저 정보 조회에 실패했습니다.")
        profile = res.json().get("response")
        if not profile:
            raise SocialLoginException("네이버 프로필 응답이 비어있습니다.")
        return cast(dict[str, Any], profile)

    def get_or_create_user(self, user_info: dict[str, Any]) -> Any:
        naver_id = str(user_info["id"])
        nickname = user_info.get("nickname") or f"naver_{naver_id[:4]}"

        social_user = (
            SocialUser.objects
            .filter(provider=SocialProvider.NAVER, provider_id=naver_id)
            .select_related("user")
            .first()
        )
        if social_user:
            return social_user.user

        unique_nickname = generate_unique_nickname(nickname[:10])
        user = User.objects.create_user(
            login_id=f"naver_{uuid.uuid4().hex[:10]}",
            name=(user_info.get("name") or nickname)[:30],
            nickname=unique_nickname,
            gender="M",
            password=None,
        )
        SocialUser.objects.create(
            provider=SocialProvider.NAVER,
            provider_id=naver_id,
            user=user,
        )
        return user

    def login(self, code: str, state: str) -> dict[str, str]:
        """code + state → 유저 조회/생성 → JWT 발급까지 처리"""
        access_token = self.get_access_token(code, state)
        user_info = self.get_user_info(access_token)
        user = self.get_or_create_user(user_info)
        return issue_jwt(user)


class GoogleOAuthService:
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def get_auth_url(self) -> str:
        """구글 인증 페이지 URL 반환"""
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"

    def get_local_auth_url(self) -> str:
        """구글 인증 페이지 URL 반환"""
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_LOCAL_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
        }
        return f"{self.AUTH_URL}?{urllib.parse.urlencode(params)}"

    def get_access_token(self, code: str) -> str:
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "code": code,
        }
        res = requests.post(self.TOKEN_URL, data=data, timeout=10)
        if not res.ok:
            print("🔴 구글 에러 응답:", res.status_code, res.json())  # 임시 추가
            raise SocialLoginException("구글 토큰 발급에 실패했습니다.")
        return cast(str, res.json()["access_token"])

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        res = requests.get(
            self.USER_INFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if not res.ok:
            raise SocialLoginException("구글 유저 정보 조회에 실패했습니다.")
        return cast(dict[str, Any], res.json())

    def get_or_create_user(self, user_info: dict[str, Any]) -> Any:
        google_id = str(user_info["id"])
        nickname = user_info.get("name") or f"google_{google_id[:4]}"

        social_user = (
            SocialUser.objects
            .filter(provider=SocialProvider.GOOGLE, provider_id=google_id)
            .select_related("user")
            .first()
        )
        if social_user:
            return social_user.user

        unique_nickname = generate_unique_nickname(nickname[:10])
        user = User.objects.create_user(
            login_id=f"google_{uuid.uuid4().hex[:10]}",
            name=nickname[:30],
            nickname=unique_nickname,
            gender="M",
            password=None,
        )
        SocialUser.objects.create(
            provider=SocialProvider.GOOGLE,
            provider_id=google_id,
            user=user,
        )
        return user

    def login(self, code: str) -> dict[str, str]:
        """code → 유저 조회/생성 → JWT 발급까지 처리"""
        access_token = self.get_access_token(code)
        user_info = self.get_user_info(access_token)
        user = self.get_or_create_user(user_info)
        return issue_jwt(user)