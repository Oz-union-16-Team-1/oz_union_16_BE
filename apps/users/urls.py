from django.urls import path

from apps.users.views.auth_views import (
    LoginView,
    LogoutView,
    SignUpView,
    TokenRefreshView,
)

urlpatterns = [
    path("signup", SignUpView.as_view(), name="signup"),
    path("login", LoginView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("token/refresh", TokenRefreshView.as_view(), name="token-refresh"),
]
