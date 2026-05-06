from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
from apps.users.serializers.check_duplication_serializers import CheckResponseSerializer
from apps.users.serializers.user_change_pwd_serializers import ChangePasswordSerializer
from apps.users.services.user_change_pwd_services import UserChangePwdService


class PasswordUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="비밀번호 변경",
        description="현재 비밀번호를 확인한 후 새로운 비밀번호로 변경합니다.",
        request=ChangePasswordSerializer,
        responses={
            200: OpenApiResponse(
                description="비밀번호 변경 성공",
                response=CheckResponseSerializer,
                examples=[
                    OpenApiExample(
                        "성공 예시 (200 OK)",
                        value={"detail": "비밀번호가 성공적으로 변경되었습니다."},
                    )
                ],
            ),
            400: OpenApiResponse(
                description="필드 누락 또는 유효성 검사 실패",
                response=ErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "필드 누락 (400 Bad Request)",
                        value={
                            "error_detail": {
                                "old_password": ["이 필드는 필수 항목입니다."]
                            }
                        },
                    )
                ],
            ),
            401: OpenApiResponse(
                description="인증 실패",
                response=ErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "인증 실패 (401 Unauthorized)",
                        value={
                            "error_detail": "자격 인증 데이터가 제공되지 않았습니다."
                        },
                    )
                ],
            ),
        },
        tags=["accounts"],
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        UserChangePwdService.update_password(
            user=request.user,
            old_password=serializer.validated_data["old_password"],
            new_password=serializer.validated_data["new_password"],
        )

        return Response(
            {"detail": "비밀번호가 성공적으로 변경되었습니다."},
            status=status.HTTP_200_OK,
        )
