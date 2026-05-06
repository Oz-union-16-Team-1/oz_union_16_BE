from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import ErrorResponseSerializer
from apps.users.serializers.user_bookmark_serializers import UserLikeBookmarkSerializer
from apps.users.services.user_bookmark_services import UserLikeBookmarkService


class BookmarkPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "results": schema,
            },
        }


@extend_schema(
    tags=["accounts"],
    summary="유저 북마크 목록 조회",
    description="로그인한 유저의 게임 좋아요 북마크 목록을 반환합니다.",
    parameters=[
        OpenApiParameter(name="page", type=int, description="페이지 번호"),
        OpenApiParameter(name="page_size", type=int, description="페이지당 항목 수"),
    ],
    responses={
        200: OpenApiResponse(
            description="북마크 목록 조회 성공 (페이징 포함)",
            # ListAPIView의 pagination_class에 의해 정의된 schema가 자동으로 적용됩니다.
            response=UserLikeBookmarkSerializer(many=True),
            examples=[
                OpenApiExample(
                    "성공 예시 (200 OK)",
                    value={
                        "count": 1,
                        "results": [
                            {
                                "id": 1,
                                "game_id": 101,
                                "game_title": "멋진 게임",
                                "created_at": "2024-03-21T10:00:00Z",
                            }
                        ],
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
                    value={"error_detail": "자격 인증 데이터가 제공되지 않았습니다."},
                )
            ],
        ),
    },
)
class UserLikeBookmarkListView(ListAPIView):
    pagination_class = BookmarkPagination
    serializer_class = UserLikeBookmarkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserLikeBookmarkService.get_user_bookmarks(self.request.user)
