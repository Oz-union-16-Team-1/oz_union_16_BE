from django.urls import path

from apps.games.view.game_list_top100_views import GameTop100View

urlpatterns = [
    path("lst/top100", GameTop100View.as_view(), name="game_list_top100"),
]
