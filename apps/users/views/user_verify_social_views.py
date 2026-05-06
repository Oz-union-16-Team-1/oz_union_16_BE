from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
from apps.users.serializers.user_verify_social_serializers import (
    UserVerifySocialSerializer,
)
from apps.users.services.user_verify_social_services import UserVerifySocialService


class UserVerifySocialView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="내 소셜 정보 조회",
        description="로그인한 계정의 소셜 정보를 조회합니다.",
        responses={200: UserVerifySocialSerializer, 401: ErrorResponseSerializer},
        examples=[
            OpenApiExample(
                "인증 실패 (401 Unauthorized)",
                value={"error_detail": "자격 인증 데이터가 제공되지 않았습니다."},
                status_codes=["401"],
            )
        ],
        tags=["accounts"],
    )
    def get(self, request):
        social_info = UserVerifySocialService.check_social_user(request.user)
        serializer = UserVerifySocialSerializer(social_info)
        return Response(serializer.data, status=status.HTTP_200_OK)
