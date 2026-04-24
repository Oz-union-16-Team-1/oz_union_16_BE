from django.conf import settings
from django.shortcuts import redirect
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.users.services.social_login_services import (
    GoogleOAuthService,
    KakaoOAuthService,
    NaverOAuthService,
)

FRONTEND_LOCAL_CALLBACK_URI = getattr(
    settings,
    "FRONTEND_LOCAL_CALLBACK_URI",
    "http://localhost:5173/auth/callback?social_login=success",
)

REFRESH_TOKEN_LIFETIME = getattr(settings, "SIMPLE_JWT", {}).get(
    "REFRESH_TOKEN_LIFETIME"
)
REFRESH_COOKIE_KEY = "refresh_token"


def _set_refresh_cookie_and_redirect(refresh_token: str) -> redirect:
    """JWT 발급 → HttpOnly 쿠키 설정 → 프론트 콜백 페이지로 redirect"""
    uri = FRONTEND_LOCAL_CALLBACK_URI

    response = redirect(uri)
    cookie_kwargs = {
        "key": REFRESH_COOKIE_KEY,
        "value": refresh_token,
        "httponly": True,
        "secure": not settings.DEBUG,
        "samesite": "Lax" if settings.DEBUG else "None",
        "path": "/",
    }
    if REFRESH_TOKEN_LIFETIME:
        cookie_kwargs["max_age"] = int(REFRESH_TOKEN_LIFETIME.total_seconds())
    response.set_cookie(**cookie_kwargs)
    return response


# ---------------------------------------------------------------------------
# Kakao
# ---------------------------------------------------------------------------


class KakaoLocalLoginView(APIView):
    """GET /api/v1/accounts/social-login/kakao/login/local"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["accounts"],
        summary="카카오 소셜 로그인 시작 로컬",
        description="카카오 OAuth 인증 페이지로 302 redirect합니다.",
        responses={
            302: OpenApiResponse(description="카카오 인증 페이지로 redirect"),
        },
    )
    def get(self, request: Request):
        service = KakaoOAuthService()
        return redirect(service.get_local_auth_url())


class KakaoLocalCallbackView(APIView):
    """GET /api/v1/accounts/social-login/kakao/callback"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["accounts"],
        summary="카카오 소셜 로그인 콜백 로컬",
        description=(
            "카카오 인증 후 전달받은 code를 처리합니다.\n\n"
            "- 신규 유저: User + SocialUser 자동 생성\n"
            "- 기존 유저: 기존 계정으로 로그인\n"
            "- Refresh Token을 HttpOnly Cookie로 설정 후 프론트 콜백 페이지로 redirect"
        ),
        parameters=[
            OpenApiParameter(
                name="code",
                location=OpenApiParameter.QUERY,
                required=True,
                description="카카오 인증 코드",
            ),
        ],
        responses={
            302: OpenApiResponse(
                description="프론트 콜백 페이지로 redirect (refresh_token 쿠키 설정)"
            ),
            502: OpenApiResponse(description="카카오 API 호출 실패"),
        },
    )
    def get(self, request: Request):
        code = request.query_params.get("code")
        tokens = KakaoOAuthService().login(code)
        return _set_refresh_cookie_and_redirect(tokens["refresh_token"])


# ---------------------------------------------------------------------------
# Naver
# ---------------------------------------------------------------------------


class NaverLocalLoginView(APIView):
    """GET /api/v1/accounts/social-login/naver/login/local"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["accounts"],
        summary="네이버 소셜 로그인 시작 로컬",
        description="네이버 OAuth 인증 페이지로 302 redirect합니다.",
        responses={
            302: OpenApiResponse(description="네이버 인증 페이지로 redirect"),
        },
    )
    def get(self, request: Request):
        service = NaverOAuthService()
        auth_url, _ = service.get_local_auth_url()
        return redirect(auth_url)


class NaverLocalCallbackView(APIView):
    """GET /api/v1/accounts/social-login/naver/callback/local"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["accounts"],
        summary="네이버 소셜 로그인 콜백 로컬",
        description=(
            "네이버 인증 후 전달받은 code와 state를 처리합니다.\n\n"
            "- 신규 유저: User + SocialUser 자동 생성\n"
            "- 기존 유저: 기존 계정으로 로그인\n"
            "- Refresh Token을 HttpOnly Cookie로 설정 후 프론트 콜백 페이지로 redirect"
        ),
        parameters=[
            OpenApiParameter(
                name="code",
                location=OpenApiParameter.QUERY,
                required=True,
                description="네이버 인증 코드",
            ),
            OpenApiParameter(
                name="state",
                location=OpenApiParameter.QUERY,
                required=True,
                description="CSRF 방어용 state 값",
            ),
        ],
        responses={
            302: OpenApiResponse(
                description="프론트 콜백 페이지로 redirect (refresh_token 쿠키 설정)"
            ),
            502: OpenApiResponse(description="네이버 API 호출 실패"),
        },
    )
    def get(self, request: Request):
        code = request.query_params.get("code")
        state = request.query_params.get("state", "")
        tokens = NaverOAuthService().login(code, state)
        return _set_refresh_cookie_and_redirect(tokens["refresh_token"])


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


class GoogleLocalLoginView(APIView):
    """
    GET /api/v1/accounts/social-login/google/local
    서비스에서 조합한 URL로 302 redirect
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["accounts"],
        summary="구글 소셜 로그인 시작 로컬",
        description="구글 OAuth 인증 페이지로 302 redirect합니다.",
        responses={
            302: OpenApiResponse(description="구글 인증 페이지로 redirect"),
        },
    )
    def get(self, request: Request):
        service = GoogleOAuthService()
        return redirect(service.get_local_auth_url())


class GoogleLocalCallbackView(APIView):
    """GET /api/v1/accounts/social-login/google/callback/local"""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["accounts"],
        summary="구글 소셜 로그인 콜백 로컬",
        description=(
            "구글 인증 후 전달받은 code를 처리합니다.\n\n"
            "- 신규 유저: User + SocialUser 자동 생성\n"
            "- 기존 유저: 기존 계정으로 로그인\n"
            "- Refresh Token을 HttpOnly Cookie로 설정 후 프론트 콜백 페이지로 redirect"
        ),
        parameters=[
            OpenApiParameter(
                name="code",
                location=OpenApiParameter.QUERY,
                required=True,
                description="구글 인증 코드",
            ),
        ],
        responses={
            302: OpenApiResponse(
                description="프론트 콜백 페이지로 redirect (refresh_token 쿠키 설정)"
            ),
            502: OpenApiResponse(description="구글 API 호출 실패"),
        },
    )
    def get(self, request: Request):
        code = request.query_params.get("code")
        tokens = GoogleOAuthService().login(code)
        return _set_refresh_cookie_and_redirect(tokens["refresh_token"])
