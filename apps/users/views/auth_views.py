from django.conf import settings
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.serializers.auth_serializers import LoginSerializer, SignUpSerializer
from apps.users.services.auth_services import AuthService

REFRESH_TOKEN_LIFETIME = getattr(settings, "SIMPLE_JWT", {}).get(
    "REFRESH_TOKEN_LIFETIME"
)
REFRESH_COOKIE_KEY = "refresh_token"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Refresh Token을 HttpOnly Cookie에 굽는 헬퍼."""
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


class SignUpView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="회원가입",
        description="새로운 유저를 등록합니다.",
        request=SignUpSerializer,
        responses={
            201: OpenApiResponse(
                description="error_detail: 회원가입이 완료되었습니다."
            ),
            400: OpenApiResponse(
                description="error_detail: 비밀번호는 8자 이상이어야 합니다."
            ),
            409: OpenApiResponse(
                description="error_detail: 이미 중복된 회원가입 내역이 존재합니다."
            ),
        },
        tags=["accounts"],
    )
    def post(self, request):
        serializer = SignUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        AuthService.sign_up(serializer.validated_data.copy())

        return Response(
            {"detail": "회원가입이 완료되었습니다."},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="로그인",
        description="로그인 아이디와 비밀번호로 토큰을 발급받습니다. Refresh Token은 쿠키에 저장됩니다.",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(
                description="로그인 성공",
                response=serializers.Serializer,  # 실제 반환하는 {'access_token': ...} 구조
            ),
            400: OpenApiResponse(
                description="error_detail: password: [이 필드는 필수 항목입니다.]"
            ),
            401: OpenApiResponse(
                description="error_detail: 로그인 아이디 또는 비밀번호가 올바르지 않습니다."
            ),
            403: OpenApiResponse(description="error_detail: 차단된 계정입니다."),
        },
        tags=["accounts"],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tokens = AuthService.login(
            login_id=serializer.validated_data["login_id"],
            password=serializer.validated_data["password"],
        )

        response = Response(
            {"access_token": tokens["access_token"]}, status=status.HTTP_200_OK
        )
        _set_refresh_cookie(response, tokens["refresh_token"])
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="로그아웃",
        description="쿠키의 Refresh Token을 무효화하고 로그아웃합니다.",
        responses={
            200: OpenApiResponse(description="detail: 로그아웃 되었습니다."),
            400: OpenApiResponse(
                description="error_detail: 인증 정보가 유효하지 않거나 만료되었습니다."
            ),
        },
        tags=["accounts"],
    )
    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_KEY)
        AuthService.logout(refresh_token)

        response = Response(
            {"detail": "로그아웃 되었습니다."}, status=status.HTTP_200_OK
        )
        response.delete_cookie(REFRESH_COOKIE_KEY, path="/")
        return response


class TokenRefreshView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="토큰 재발급",
        description="쿠키의 Refresh Token을 이용해 새로운 Access/Refresh Token을 발급합니다.",
        responses={
            200: OpenApiResponse(description="access_token: JWT Access Token Value"),
            400: OpenApiResponse(
                description="error_detail: { refresh_token: [이 필드는 필수 항목입니다.] }"
            ),
            403: OpenApiResponse(
                description="error_detail: 로그인 세션이 만료되었습니다."
            ),
        },
        tags=["accounts"],
    )
    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_KEY)
        tokens = AuthService.refresh(refresh_token)

        response = Response(
            {"access_token": tokens["access_token"]}, status=status.HTTP_200_OK
        )
        _set_refresh_cookie(response, tokens["refresh_token"])
        return response
