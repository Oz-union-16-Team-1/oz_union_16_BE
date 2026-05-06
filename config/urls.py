from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin  # type: ignore
from django.urls import include, path  # type: ignore
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/games/", include("apps.games.urls")),
    path("api/v1/match/", include("apps.match.urls")),
    path("api/v1/survey/", include("apps.survey.urls")),
    path("api/v1/accounts/", include("apps.users.urls")),
    path("api/v1/chatbot/", include("apps.chatbot.urls.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/swagger/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
    ]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
