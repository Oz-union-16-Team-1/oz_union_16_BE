from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
from apps.games.serializer.game_list_detail_serializers import (
    GameListDetailResponseSerializer,
)
from apps.games.service.game_list_detail_services import (
    GameDetailNotFoundError,
    GameListDetailService,
)


class GameListDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="게임 상세 조회",
        tags=["game"],
        parameters=[
            OpenApiParameter(
                name="game_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="조회할 게임 ID",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=GameListDetailResponseSerializer,
                description="게임 상세 조회 성공",
                examples=[
                    OpenApiExample(
                        "성공 응답",
                        value={
                            "game_id": 501,
                            "title": "엘든 링: 황금 나무의 그림자",
                            "genres": ["액션", "역할수행(RPG)"],
                            "release_date": "2024-06-21",
                            "developer": "FromSoftware",
                            "publisher": "Bandai Namco",
                            "media": {
                                "promo_video_url": "https://www.youtube.com/watch?v=example",
                                "promo_embed_url": "https://www.youtube.com/embed/example",
                                "cover_image_url": "https://images.igdb.com/igdb/image/upload/t_1080p/co1234.jpg",
                            },
                            "description": "그림자의 땅에서 펼쳐지는 새로운 모험과 강력한 보스들과의 전투.",
                            "external_links": {
                                "official_site": "https://www.eldenring.com",
                                "steam": "https://store.steampowered.com/app/eldenring",
                                "epic_store": None,
                            },
                            "is_liked": False,
                            "like_count": 1250,
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="게임을 찾을 수 없음",
                examples=[
                    OpenApiExample(
                        "게임 없음",
                        value={"error_detail": "해당 게임을 찾을 수 없습니다."},
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
    )
    def get(self, request, game_id: int):
        try:
            data = GameListDetailService.get_game_detail(
                game_id=game_id,
                user=request.user,
            )
        except GameDetailNotFoundError as exc:
            return Response(
                {"error_detail": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(data, status=status.HTTP_200_OK)
