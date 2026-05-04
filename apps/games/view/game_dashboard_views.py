from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.games.models import Game
from apps.games.serializer.game_dashboard_serializers import GameDashboardSerializer
from apps.games.service.game_dashboard_services import GameDashboardService


class GameDashboardView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="관리자 게임 대시보드 상세 조회",
        tags=["game-admin"],
        responses={
            200: GameDashboardSerializer,
            403: {"example": {"detail": "관리자 권한이 필요합니다."}},
            404: {"example": {"error_detail": "게임을 찾을 수 없습니다."}},
        },
    )
    def get(self, request, game_id: int):
        try:
            dashboard = GameDashboardService.get_dashboard(game_id)
        except Game.DoesNotExist:
            return Response(
                {"error_detail": "게임을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = GameDashboardSerializer(dashboard)
        return Response(serializer.data, status=status.HTTP_200_OK)
