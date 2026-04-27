from django.urls import path

from apps.match.views.candidates import MatchCandidatesAPIView
from apps.match.views.genre_image import MatchGenreImageAPIView
from apps.match.views.rating_responses import MatchResponsesAPIView

urlpatterns = [
    path(
        "candidates",
        MatchCandidatesAPIView.as_view(),
        name="match-candidates",
    ),
    path(
        "genres/image-url",
        MatchGenreImageAPIView.as_view(),
        name="match-genres-image-url",
    ),
    path(
        "responses",
        MatchResponsesAPIView.as_view(),
        name="match-responses",
    ),
]
