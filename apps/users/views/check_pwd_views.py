from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
from apps.users.serializers.check_duplication_serializers import CheckResponseSerializer
from apps.users.serializers.check_pwd_serializers import PasswordCheckSerializer
from apps.users.services.check_pwd_services import CheckPwdService


class PasswordCheckView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="비밀번호 확인",
        description="회원 탈퇴 등 민감한 작업 전 비밀번호를 검증합니다.",
        request=PasswordCheckSerializer,
        responses={
            200: CheckResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
        },
        examples=[
            OpenApiExample(
                "성공 예시 (200 OK)",
                value={"detail": "비밀번호 확인에 성공했습니다."},
                status_codes=["200"],
            ),
            OpenApiExample(
                "인증 실패2 (401 Unauthorized)",
                value={"error_detail": "비밀번호가 일치하지 않습니다."},
                status_codes=["401"],
            ),
            OpenApiExample(
                "인증 실패 (401 Unauthorized)",
                value={"error_detail": "자격 인증 데이터가 제공되지 않았습니다."},
                status_codes=["401"],
            ),
            OpenApiExample(
                "필드 누락 (400 Bad Request)",
                value={"error_detail": {"password": ["이 필드는 필수 항목입니다."]}},
                status_codes=["400"],
            ),
        ],
        tags=["accounts"],
    )
    def post(self, request):
        serializer = PasswordCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        CheckPwdService.check_user_password(
            request.user, serializer.validated_data["password"]
        )

        return Response(
            {"detail": "비밀번호 확인에 성공했습니다."}, status=status.HTTP_200_OK
        )
