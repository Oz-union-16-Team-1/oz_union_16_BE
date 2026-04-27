from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.exceptions import ErrorResponseSerializer
from apps.users.serializers.check_duplication_serializers import (
    CheckIdSerializer,
    CheckNickNameSerializer,
    CheckResponseSerializer,
)
from apps.users.services.check_duplication_services import CheckService


class CheckIdView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = CheckIdSerializer

    @extend_schema(
        summary="아이디 중복 체크",
        description="입력받은 login_id가 데이터베이스에 존재하는지 확인합니다.",
        responses={
            200: CheckResponseSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
        tags=["accounts"],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = CheckService.check_id(serializer.validated_data["login_id"])

        response_data = CheckResponseSerializer({"detail": message}).data
        return Response(response_data, status=status.HTTP_200_OK)


class CheckNickNameView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = CheckNickNameSerializer

    @extend_schema(
        summary="닉네임 중복 체크",
        description="입력받은 nickname이 데이터베이스에 존재하는지 확인합니다.",
        responses={
            200: CheckResponseSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        },
        tags=["accounts"],
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = CheckService.check_nickname(serializer.validated_data["nickname"])

        response_data = CheckResponseSerializer({"detail": message}).data
        return Response(response_data, status=status.HTTP_200_OK)
