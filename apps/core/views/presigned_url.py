from typing import Any

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.serializers.presigned_url_serializer import PresignedUrlRequestSerializer
from apps.users.services.user_presigned_url_services import PresignedUrlService


class BasePresignedUrlView(APIView):
    permission_classes = [IsAuthenticated]
    folder: str = ""

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PresignedUrlRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = PresignedUrlService.create(
            folder=self.folder,
            file_name=serializer.validated_data["file_name"],
            content_type=serializer.validated_data["content_type"],  # 추가
        )

        return Response(result, status=status.HTTP_200_OK)
