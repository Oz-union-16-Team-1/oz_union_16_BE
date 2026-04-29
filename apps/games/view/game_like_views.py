from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
from apps.games.serializer.game_like_serializers import GameLikeResponseSerializer
from apps.games.service.game_like_services import (
    GameLikeBookmarkNotFoundError,
    GameLikeGameNotFoundError,
    GameLikeService,
)


class GameLikeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="게임 좋아요",
        tags=["game"],
        parameters=[
            OpenApiParameter(
                name="game_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="좋아요할 게임 ID",
            ),
        ],
        responses={
            201: OpenApiResponse(
                response=GameLikeResponseSerializer,
                description="게임 좋아요 성공",
                examples=[
                    OpenApiExample(
                        "성공 응답",
                        value={
                            "game_id": 501,
                            "like_count": 1251,
                        },
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="인증 실패",
                examples=[
                    OpenApiExample(
                        "인증 실패",
                        value={
                            "error_detail": "자격 인증 데이터가 제공되지 않았습니다."
                        },
                        response_only=True,
                        status_codes=["401"],
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
    def post(self, request, game_id: int):
        try:
            data = GameLikeService.like_game(
                user=request.user,
                game_id=game_id,
            )
        except GameLikeGameNotFoundError as exc:
            return Response(
                {"error_detail": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="게임 좋아요 취소",
        tags=["game"],
        parameters=[
            OpenApiParameter(
                name="game_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="좋아요 취소할 게임 ID",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=GameLikeResponseSerializer,
                description="게임 좋아요 취소 성공",
                examples=[
                    OpenApiExample(
                        "성공 응답",
                        value={
                            "game_id": 501,
                            "like_count": 1250,
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="인증 실패",
                examples=[
                    OpenApiExample(
                        "인증 실패",
                        value={
                            "error_detail": "자격 인증 데이터가 제공되지 않았습니다."
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="게임 또는 좋아요 기록을 찾을 수 없음",
                examples=[
                    OpenApiExample(
                        "좋아요 기록 없음",
                        value={"error_detail": "좋아요 기록을 찾을 수 없습니다."},
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
    )
    def delete(self, request, game_id: int):
        try:
            data = GameLikeService.unlike_game(
                user=request.user,
                game_id=game_id,
            )
        except (GameLikeGameNotFoundError, GameLikeBookmarkNotFoundError) as exc:
            return Response(
                {"error_detail": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(data, status=status.HTTP_200_OK)
