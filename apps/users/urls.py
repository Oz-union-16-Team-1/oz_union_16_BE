from django.urls import path

from apps.users.views.auth_views import (
    LoginView,
    LogoutView,
    SignUpView,
    TokenRefreshView,
)
from apps.users.views.check_duplication_views import CheckIdView, CheckNickNameView
from apps.users.views.social_login_local_views import (
    GoogleLocalCallbackView,
    GoogleLocalLoginView,
    KakaoLocalCallbackView,
    KakaoLocalLoginView,
    NaverLocalCallbackView,
    NaverLocalLoginView,
)
from apps.users.views.social_login_views import (
    GoogleCallbackView,
    GoogleLoginView,
    KakaoCallbackView,
    KakaoLoginView,
    NaverCallbackView,
    NaverLoginView,
)
from apps.users.views.user_change_pwd_views import PasswordUpdateView
from apps.users.views.user_info_views import UserInfoView

urlpatterns = [
    path("signup", SignUpView.as_view(), name="signup"),  # Auth
    path("login", LoginView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("token/refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path(
        "social-login/kakao", KakaoLoginView.as_view(), name="kakao-login"
    ),  # SocialLogin
    path("social-login/naver", NaverLoginView.as_view(), name="naver-login"),
    path("social-login/google", GoogleLoginView.as_view(), name="google-login"),
    path(
        "social-login/kakao/callback",
        KakaoCallbackView.as_view(),
        name="kakao-callback",
    ),
    path(
        "social-login/naver/callback",
        NaverCallbackView.as_view(),
        name="naver-callback",
    ),
    path(
        "social-login/google/callback",
        GoogleCallbackView.as_view(),
        name="google-callback",
    ),
    path(
        "social-login/kakao/local",
        KakaoLocalLoginView.as_view(),
        name="kakao-local-login",
    ),  # Local SocialLogin
    path(
        "social-login/naver/local",
        NaverLocalLoginView.as_view(),
        name="naver-local-login",
    ),
    path(
        "social-login/google/local",
        GoogleLocalLoginView.as_view(),
        name="google-local-login",
    ),
    path(
        "social-login/kakao/callback/local",
        KakaoLocalCallbackView.as_view(),
        name="kakao-local-callback",
    ),
    path(
        "social-login/naver/callback/local",
        NaverLocalCallbackView.as_view(),
        name="naver-local-callback",
    ),
    path(
        "social-login/google/callback/local",
        GoogleLocalCallbackView.as_view(),
        name="google-local-callback",
    ),
    path("check-nickname", CheckNickNameView.as_view(), name="check-nickname"),
    path("check-id", CheckIdView.as_view(), name="check-id"),
    path("me", UserInfoView.as_view(), name="user-info"),
    path("me/change-password", PasswordUpdateView.as_view(), name="change-password"),
]
