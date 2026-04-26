from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.serializers.user_info_serializers import UserInfoSerializer
from apps.users.services.user_info_services import UserInfoService


class UserInfoView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserInfoSerializer

    @extend_schema(
        summary="내 정보 조회",
        description="현재 로그인한 사용자의 프로필 정보를 가져옵니다.",
        responses={200: UserInfoSerializer},
    )
    def get(self, request):
        user = UserInfoService.get_user_info(request.user)
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
