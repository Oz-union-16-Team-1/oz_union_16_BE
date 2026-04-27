from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.serializers.check_pwd_serializers import PasswordCheckSerializer
from apps.users.services.check_pwd_services import CheckPwdService


class PasswordCheckView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="비밀번호 확인",
        description="회원 탈퇴 등 민감한 작업 전 비밀번호를 검증합니다.",
        request=PasswordCheckSerializer,
        responses={
            200: None,
        },
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
