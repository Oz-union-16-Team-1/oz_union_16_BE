from django.contrib import admin  # type: ignore
from django.urls import include, path  # type: ignore

urlpatterns = [
    path("admin/", admin.site.urls),
    path("chatbot/", include("apps.chatbot.urls")),
    path("games/", include("apps.games.urls")),
    path("match/", include("apps.match.urls")),
    path("survey/", include("apps.survey.urls")),
    path("users/", include("apps.users.urls")),
]
