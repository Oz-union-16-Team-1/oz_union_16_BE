from typing import Any

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
from apps.core.serializers.presigned_url_serializer import (
    PresignedUrlRequestSerializer,
    PresignedUrlResponseSerializer,
)
from apps.core.views.presigned_url import BasePresignedUrlView
from apps.users.serializers.check_duplication_serializers import CheckResponseSerializer
from apps.users.serializers.user_presigned_url_serializers import (
    ProfileImageUpdateSerializer,
)
from apps.users.services.user_presigned_url_services import PresignedUrlService


class ProfileImagePresignedUrlView(BasePresignedUrlView):
    folder = "profiles"

    @extend_schema(
        tags=["accounts"],
        summary="프로필 이미지 업로드용 Presigned URL 발급",
        request=PresignedUrlRequestSerializer,
        responses={
            200: OpenApiResponse(
                description="Presigned URL 발급 성공",
                response=PresignedUrlResponseSerializer,
            ),
            400: OpenApiResponse(
                description="잘못된 요청",
                response=ErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "필드 오류 (400 Bad Request)",
                        value={"error_detail": "지원하지 않는 파일 형식입니다."},
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
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().post(request, *args, **kwargs)


class ProfileImageUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["accounts"],
        summary="프로필 이미지 등록",
        request=ProfileImageUpdateSerializer,
        responses={
            200: OpenApiResponse(
                description="이미지 등록 성공",
                response=CheckResponseSerializer,
                examples=[
                    OpenApiExample(
                        "성공 예시 (200 OK)",
                        value={"detail": "프로필 사진이 등록되었습니다."},
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
    )
    def put(self, request: Request) -> Response:
        serializer = ProfileImageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        PresignedUrlService.update_profile_image(
            user=request.user,
            profile_img_url=serializer.validated_data["profile_img_url"],
        )

        return Response(
            {"detail": "프로필 사진이 등록되었습니다."}, status=status.HTTP_200_OK
        )
