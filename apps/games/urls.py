from django.urls import path

from apps.games.view.game_dashboard_views import GameDashboardView
from apps.games.view.game_like_views import GameLikeView
from apps.games.view.game_list_detail_views import GameListDetailView
from apps.games.view.game_list_top100_views import GameTop100View

urlpatterns = [
    path("list/top100", GameTop100View.as_view(), name="game_list_top100"),
    path(
        "<int:game_id>/dashboard",
        GameDashboardView.as_view(),
        name="game_dashboard",
    ),
    path("list/<int:game_id>", GameListDetailView.as_view(), name="game_list_detail"),
    path("<int:game_id>/like", GameLikeView.as_view(), name="game_like"),
]
