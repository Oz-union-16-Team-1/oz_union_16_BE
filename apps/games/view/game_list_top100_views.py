from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.games.serializer.game_list_top100_serializers import GameTop100Serializer
from apps.games.service.game_list_top100_services import GameTop100Service


class GameTop100View(APIView):
    @extend_schema(
        summary="인기 TOP 100 게임 조회",
        tags=["game"],
        parameters=[
            OpenApiParameter(
                # description 수정: 0(전체) 포함 명시
                name="genre_id",
                type=int,
                required=True,
                description="장르 ID (0: 전체, 1~14: 특정 장르)",
            )
        ],
        responses={
            200: GameTop100Serializer(many=True),
            400: {
                "example": {
                    "error_detail": "유효하지 않은 장르 ID입니다. (0~14 사이의 값을 입력해주세요)"
                }
            },
        },
    )
    def get(self, request):
        genre_id = request.query_params.get("genre_id")

        # 1. 유효성 검사 (입력값 유무 및 범위 체크)
        if (
            genre_id is None
        ):  # genre_id=0 도 통과할 수 있도록 is None으로 체크하는 게 안전합니다.
            return Response(
                {"error_detail": "genre_id는 필수 입력값입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            g_id = int(genre_id)
            # [수정 포인트]: 1 -> 0으로 변경하여 '전체' 카테고리 허용
            if not (0 <= g_id <= 14):
                raise ValueError
        except ValueError:
            return Response(
                {
                    # 에러 메시지 가독성 수정
                    "error_detail": "유효하지 않은 장르 ID입니다. (0~14 사이의 값을 입력해주세요)"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. 조회 및 결과 반환
        try:
            top_games = GameTop100Service.get_top_100_games(g_id)
            serializer = GameTop100Serializer(top_games, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception:
            return Response(
                {"error_detail": "서버 오류가 발생했습니다."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
