from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
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
        description="로그인한 계정의 정보를 조회합니다.",
        responses={
            200: UserInfoSerializer,
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
    def get(self, request):
        user = UserInfoService.get_user_info(request.user)
        serializer = UserInfoSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="회원 정보 수정",
        description="로그인한 계정의 닉네임이나 프로필url을 수정합니다.",
        request=UserUpdateSerializer,
        responses={
            200: OpenApiResponse(
                description="정보 수정 성공",
                response=UserUpdateResponseSerializer,
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
            409: OpenApiResponse(
                description="닉네임 중복",
                response=ErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "중복 오류 (409 Conflict)",
                        value={
                            "error_detail": {
                                "nickname": ["중복된 닉네임이 존재합니다."]
                            }
                        },
                    )
                ],
            ),
        },
        tags=["accounts"],
    )
    def patch(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        updated_data = UserInfoService.update_user_profile_nickname(
            user=request.user, data=serializer.validated_data
        )

        response_serializer = UserUpdateResponseSerializer(updated_data)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="회원 탈퇴",
        description="비밀번호를 입력받아 계정을 삭제합니다.",
        responses={
            204: OpenApiResponse(description="회원 탈퇴 성공 (반환 데이터 없음)"),
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
    def delete(self, request):
        UserInfoService.delete_user(request.user)
        return Response(
            {"detail": "회원 탈퇴가 완료되었습니다."}, status=status.HTTP_204_NO_CONTENT
        )
