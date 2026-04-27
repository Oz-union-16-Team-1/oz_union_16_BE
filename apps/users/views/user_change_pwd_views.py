from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.serializers.user_change_pwd_serializers import ChangePasswordSerializer
from apps.users.services.user_change_pwd_services import UserChangePwdService


class PasswordUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="비밀번호 변경",
        description="현재 비밀번호를 확인한 후 새로운 비밀번호로 변경합니다.",
        request=ChangePasswordSerializer,
        responses={200: None},
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
