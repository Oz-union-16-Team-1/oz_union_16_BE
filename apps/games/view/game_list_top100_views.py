from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ErrorResponseSerializer
from apps.games.serializer.game_list_top100_serializers import (
    GameTop100ListResponseSerializer,
    GameTop100Serializer,
)
from apps.games.service.game_list_top100_services import GameTop100Service


class GameTop100View(APIView):
    PAGE_SIZE_DEFAULT = 20
    PAGE_SIZE_MAX = 100
    VALID_GENRE_IDS = list(range(0, 15))

    @extend_schema(
        summary="게임 목록 TOP 100 조회",
        tags=["game"],
        parameters=[
            OpenApiParameter(
                name="genre_id",
                type=int,
                required=True,
                description="장르 ID (0: 전체, 1~14: 각 장르)",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                required=False,
                description="게임 제목 앞부분 검색어",
            ),
            OpenApiParameter(
                name="fuzzy",
                type=bool,
                required=False,
                description="true이면 공백으로 나눈 단어 중 하나가 제목 앞부분과 일치할 때 검색",
            ),
            OpenApiParameter(name="page", type=int, required=False),
            OpenApiParameter(name="page_size", type=int, required=False),
        ],
        responses={
            200: OpenApiResponse(
                response=GameTop100ListResponseSerializer,
                description=(
                    "전체 장르(genre_id=0)는 2026~2024년 평가 수 50개 이상 후보를 우선 조회하고 "
                    "부족하면 2023년부터 2020년까지 평가 수 50개 이상 후보를 보충합니다. "
                    "개별 장르(genre_id=1~14)는 최신 연도부터 평가 수 50개, 30개, 10개, 5개 이상 후보 순서로 보충합니다."
                ),
                examples=[
                    OpenApiExample(
                        "성공 응답",
                        value={
                            "ranked_at": "2026-04-08T20:10:00+09:00",
                            "count": 100,
                            "next": 2,
                            "results": [
                                {
                                    "game_id": 1942,
                                    "name": "예시 게임 (Example Game)",
                                    "genres": ["전략", "시뮬레이션"],
                                    "thumbnail_url": "https://cdn.example.com/1942.jpg",
                                    "rating": 88.4,
                                    "is_liked": False,
                                    "like_count": 123,
                                }
                            ],
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="잘못된 요청",
                examples=[
                    OpenApiExample(
                        "genre_id 오류",
                        value={"error_detail": "유효하지 않은 장르 ID입니다."},
                        response_only=True,
                        status_codes=["400"],
                    )
                ],
            ),
            503: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="서비스 일시 장애",
                examples=[
                    OpenApiExample(
                        "서비스 장애",
                        value={"error_detail": "서비스 이용이 일시적으로 불가합니다."},
                        response_only=True,
                        status_codes=["503"],
                    )
                ],
            ),
        },
    )
    def get(self, request):
        genre_id_raw = request.query_params.get("genre_id")
        if genre_id_raw is None:
            return Response(
                {"error_detail": "genre_id 파라미터가 누락되었습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            g_id = int(genre_id_raw)
            if g_id not in self.VALID_GENRE_IDS:
                return Response(
                    {"error_detail": "유효하지 않은 장르 ID입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            page = max(int(request.query_params.get("page", 1)), 1)
            page_size = min(
                int(request.query_params.get("page_size", self.PAGE_SIZE_DEFAULT)),
                self.PAGE_SIZE_MAX,
            )

            try:
                all_games = GameTop100Service.get_top_100_games(
                    genre_id=g_id,
                    search=request.query_params.get("search", ""),
                    fuzzy=request.query_params.get("fuzzy", "false").lower() == "true",
                )
            except Exception:
                return Response(
                    {"error_detail": "서비스 이용이 일시적으로 불가합니다."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            total_count = len(all_games)
            start = (page - 1) * page_size
            end = start + page_size
            page_games = all_games[start:end]

            liked_game_ids = set()
            if request.user.is_authenticated:
                liked_game_ids = set(
                    request.user.like_bookmarks.values_list("game_id", flat=True)
                )

            serializer = GameTop100Serializer(
                page_games,
                many=True,
                context={"request": request, "liked_game_ids": liked_game_ids},
            )

            return Response(
                {
                    "ranked_at": timezone.now().isoformat(),
                    "count": total_count,
                    "next": page + 1 if end < total_count else None,
                    "results": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError, TypeError:
            return Response(
                {"error_detail": "파라미터 형식이 올바르지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            return Response(
                {"error_detail": "서버 내부 오류"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
