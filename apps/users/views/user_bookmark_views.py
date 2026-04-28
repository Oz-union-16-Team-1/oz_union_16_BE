from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.serializers.user_bookmark_serializers import UserLikeBookmarkSerializer
from apps.users.services.user_bookmark_services import UserLikeBookmarkService


class BookmarkPagination(PageNumberPagination):
    page_size = 10  # 기본값
    page_size_query_param = "page_size"  # page_size 쿼리 파라미터 활성화
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
    responses={200: UserLikeBookmarkSerializer(many=True)},
)
class UserLikeBookmarkListView(ListAPIView):
    pagination_class = BookmarkPagination
    serializer_class = UserLikeBookmarkSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserLikeBookmarkService.get_user_bookmarks(self.request.user)
