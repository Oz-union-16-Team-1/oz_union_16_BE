from django.urls import path

from apps.games.view.game_list_detail_views import GameListDetailView
from apps.games.view.game_list_top100_views import GameTop100View

urlpatterns = [
    path("list/top100", GameTop100View.as_view(), name="game_list_top100"),
    path("list/<int:game_id>", GameListDetailView.as_view(), name="game_list_detail"),
]
