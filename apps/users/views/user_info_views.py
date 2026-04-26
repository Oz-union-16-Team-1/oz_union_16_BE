from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.serializers.user_info_serializers import (
    UserInfoSerializer,
    UserUpdateResponseSerializer,
    UserUpdateSerializer,
)
from apps.users.services.user_info_services import UserInfoService


class UserInfoView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="내 정보 조회",
        responses={200: UserInfoSerializer},
        tags=["accounts"],
    )
    def get(self, request):
        user = UserInfoService.get_user_info(request.user)
        serializer = UserInfoSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="내 정보 수정",
        request=UserUpdateSerializer,
        responses={200: UserUpdateResponseSerializer},
        tags=["accounts"],
    )
    def patch(self, request):
        # APIView에서는 self.get_serializer 대신 직접 호출
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        updated_data = UserInfoService.update_user_profile_nickname(
            user=request.user, data=serializer.validated_data
        )

        response_serializer = UserUpdateResponseSerializer(updated_data)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
