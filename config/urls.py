from django.contrib import admin  # type: ignore
from django.urls import include, path  # type: ignore
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("admin/", admin.site.urls),
    path("chatbot/", include("apps.chatbot.urls")),
    path("api/v1/games/", include("apps.games.urls")),
    path("api/v1/match/", include("apps.match.urls")),
    path("survey/", include("apps.survey.urls")),
    path("api/v1/accounts/", include("apps.users.urls")),
    path("api/v1/chatbot/", include("apps.chatbot.urls.urls")),
]
