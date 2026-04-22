from django.urls import path

from apps.match.views.genre_image import MatchGenreImageAPIView

urlpatterns = [
    path(
        "genres/image-url",
        MatchGenreImageAPIView.as_view(),
        name="match-genres-image-url",
    ),
]
