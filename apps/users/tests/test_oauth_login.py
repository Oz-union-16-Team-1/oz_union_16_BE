import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.choices import SocialProvider
from apps.users.models import SocialUser, User

# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------


def make_login_id() -> str:
    return f"user_{uuid.uuid4().hex[:8]}"


def make_nickname() -> str:
    return f"nick_{uuid.uuid4().hex[:6]}"


def create_user(**kwargs) -> User:
    defaults = {
        "login_id": make_login_id(),
        "name": "홍길동",
        "nickname": make_nickname(),
        "gender": "M",
        "password": None,
    }
    defaults.update(kwargs)
    password = defaults.pop("password")
    user = User(**defaults)
    if password:
        user.set_password(password)
    else:
        user.set_unusable_password()
    user.save()
    return user


def fake_token_response(access_token: str = "fake_access_token") -> MagicMock:
    """provider 토큰 발급 API 응답 mock"""
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = {"access_token": access_token}
    return mock


# ---------------------------------------------------------------------------
# Kakao
# ---------------------------------------------------------------------------

KAKAO_USER_INFO = {
    "id": 123456789,
    "kakao_account": {
        "profile": {
            "nickname": "카카오유저",
            "profile_image_url": "",
        },
        "email": "kakao@example.com",
    },
}


def fake_kakao_user_info_response(user_info: dict = None) -> MagicMock:
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = user_info or KAKAO_USER_INFO
    return mock


class KakaoLoginViewTest(TestCase):
    """GET /api/v1/accounts/social-login/kakao/login → 카카오 인증 페이지로 302 redirect"""

    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("kakao-login")

    def test_redirect_to_kakao_auth(self) -> None:
        """카카오 로그인 URL로 접근 시 카카오 인증 페이지로 redirect"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("kauth.kakao.com/oauth/authorize", response["Location"])


class KakaoCallbackViewTest(TestCase):
    """GET /api/v1/accounts/social-login/kakao/callback"""

    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("kakao-callback")

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_new_user_success(self, mock_post, mock_get) -> None:
        """신규 유저 - 유저/SocialUser 생성 후 프론트로 redirect, refresh_token 쿠키 설정 확인"""
        mock_post.return_value = fake_token_response()
        mock_get.return_value = fake_kakao_user_info_response()

        response = self.client.get(self.url, {"code": "test_code"})

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        # 프론트 콜백 URL로 redirect됐는지 확인
        self.assertIn("refresh_token", response.cookies)
        self.assertTrue(response.cookies["refresh_token"]["httponly"])
        # DB에 유저와 SocialUser가 생성됐는지 확인
        self.assertTrue(
            SocialUser.objects.filter(
                provider=SocialProvider.KAKAO, provider_id="123456789"
            ).exists()
        )

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_existing_social_user_success(self, mock_post, mock_get) -> None:
        """기존 소셜 유저 - 새 유저 생성 없이 기존 유저로 로그인"""
        existing_user = create_user()
        SocialUser.objects.create(
            provider=SocialProvider.KAKAO,
            provider_id="123456789",
            user=existing_user,
        )
        user_count_before = User.objects.count()

        mock_post.return_value = fake_token_response()
        mock_get.return_value = fake_kakao_user_info_response()

        response = self.client.get(self.url, {"code": "test_code"})

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("refresh_token", response.cookies)
        # 새 유저가 생성되지 않았는지 확인
        self.assertEqual(User.objects.count(), user_count_before)

    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_token_api_fail(self, mock_post) -> None:
        """카카오 토큰 발급 API 실패 시 502"""
        mock_post.return_value = MagicMock(ok=False)

        response = self.client.get(self.url, {"code": "invalid_code"})

        self.assertEqual(response.status_code, 502)

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_user_info_api_fail(self, mock_post, mock_get) -> None:
        """카카오 유저 정보 API 실패 시 502"""
        mock_post.return_value = fake_token_response()
        mock_get.return_value = MagicMock(ok=False)

        response = self.client.get(self.url, {"code": "test_code"})

        self.assertEqual(response.status_code, 502)


# ---------------------------------------------------------------------------
# Naver
# ---------------------------------------------------------------------------

NAVER_USER_INFO = {
    "id": "naver_id_001",
    "nickname": "네이버유저",
    "name": "홍길동",
    "email": "naver@example.com",
    "gender": "M",
    "mobile": "010-1234-5678",
}


def fake_naver_user_info_response(user_info: dict = None) -> MagicMock:
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = {
        "resultcode": "00",
        "message": "success",
        "response": user_info or NAVER_USER_INFO,
    }
    return mock


class NaverLoginViewTest(TestCase):
    """GET /api/v1/accounts/social-login/naver/login → 네이버 인증 페이지로 302 redirect"""

    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("naver-login")

    def test_redirect_to_naver_auth(self) -> None:
        """네이버 로그인 URL로 접근 시 네이버 인증 페이지로 redirect"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("nid.naver.com/oauth2.0/authorize", response["Location"])


class NaverCallbackViewTest(TestCase):
    """GET /api/v1/accounts/social-login/naver/callback"""

    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("naver-callback")

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_new_user_success(self, mock_post, mock_get) -> None:
        """신규 유저 - 유저/SocialUser 생성 후 프론트로 redirect, refresh_token 쿠키 설정 확인"""
        mock_post.return_value = fake_token_response()
        mock_get.return_value = fake_naver_user_info_response()

        response = self.client.get(
            self.url, {"code": "test_code", "state": "test_state"}
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("refresh_token", response.cookies)
        self.assertTrue(response.cookies["refresh_token"]["httponly"])
        self.assertTrue(
            SocialUser.objects.filter(
                provider=SocialProvider.NAVER, provider_id="naver_id_001"
            ).exists()
        )

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_existing_social_user_success(self, mock_post, mock_get) -> None:
        """기존 소셜 유저 - 새 유저 생성 없이 기존 유저로 로그인"""
        existing_user = create_user()
        SocialUser.objects.create(
            provider=SocialProvider.NAVER,
            provider_id="naver_id_001",
            user=existing_user,
        )
        user_count_before = User.objects.count()

        mock_post.return_value = fake_token_response()
        mock_get.return_value = fake_naver_user_info_response()

        response = self.client.get(
            self.url, {"code": "test_code", "state": "test_state"}
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("refresh_token", response.cookies)
        self.assertEqual(User.objects.count(), user_count_before)

    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_token_api_fail(self, mock_post) -> None:
        """네이버 토큰 발급 API 실패 시 502"""
        mock_post.return_value = MagicMock(ok=False)

        response = self.client.get(
            self.url, {"code": "invalid_code", "state": "test_state"}
        )

        self.assertEqual(response.status_code, 502)

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_user_info_api_fail(self, mock_post, mock_get) -> None:
        """네이버 유저 정보 API 실패 시 502"""
        mock_post.return_value = fake_token_response()
        mock_get.return_value = MagicMock(ok=False)

        response = self.client.get(
            self.url, {"code": "test_code", "state": "test_state"}
        )

        self.assertEqual(response.status_code, 502)


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

GOOGLE_USER_INFO = {
    "id": "google_id_001",
    "name": "구글유저",
    "email": "google@example.com",
    "picture": "",
}


def fake_google_user_info_response(user_info: dict = None) -> MagicMock:
    mock = MagicMock()
    mock.ok = True
    mock.json.return_value = user_info or GOOGLE_USER_INFO
    return mock


class GoogleLoginViewTest(TestCase):
    """GET /api/v1/accounts/social-login/google/login → 구글 인증 페이지로 302 redirect"""

    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("google-login")

    def test_redirect_to_google_auth(self) -> None:
        """구글 로그인 URL로 접근 시 구글 인증 페이지로 redirect"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("accounts.google.com/o/oauth2/v2/auth", response["Location"])


class GoogleCallbackViewTest(TestCase):
    """GET /api/v1/accounts/social-login/google/callback"""

    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("google-callback")

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_new_user_success(self, mock_post, mock_get) -> None:
        """신규 유저 - 유저/SocialUser 생성 후 프론트로 redirect, refresh_token 쿠키 설정 확인"""
        mock_post.return_value = fake_token_response()
        mock_get.return_value = fake_google_user_info_response()

        response = self.client.get(self.url, {"code": "test_code"})

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("refresh_token", response.cookies)
        self.assertTrue(response.cookies["refresh_token"]["httponly"])
        self.assertTrue(
            SocialUser.objects.filter(
                provider=SocialProvider.GOOGLE, provider_id="google_id_001"
            ).exists()
        )

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_existing_social_user_success(self, mock_post, mock_get) -> None:
        """기존 소셜 유저 - 새 유저 생성 없이 기존 유저로 로그인"""
        existing_user = create_user()
        SocialUser.objects.create(
            provider=SocialProvider.GOOGLE,
            provider_id="google_id_001",
            user=existing_user,
        )
        user_count_before = User.objects.count()

        mock_post.return_value = fake_token_response()
        mock_get.return_value = fake_google_user_info_response()

        response = self.client.get(self.url, {"code": "test_code"})

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("refresh_token", response.cookies)
        self.assertEqual(User.objects.count(), user_count_before)

    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_token_api_fail(self, mock_post) -> None:
        """구글 토큰 발급 API 실패 시 502"""
        mock_post.return_value = MagicMock(ok=False)

        response = self.client.get(self.url, {"code": "invalid_code"})

        self.assertEqual(response.status_code, 502)

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_callback_user_info_api_fail(self, mock_post, mock_get) -> None:
        """구글 유저 정보 API 실패 시 502"""
        mock_post.return_value = fake_token_response()
        mock_get.return_value = MagicMock(ok=False)

        response = self.client.get(self.url, {"code": "test_code"})

        self.assertEqual(response.status_code, 502)


# ---------------------------------------------------------------------------
# 닉네임 중복 처리
# ---------------------------------------------------------------------------


class NicknameDeduplicationTest(TestCase):
    """소셜 로그인 신규 가입 시 닉네임 중복 처리 확인"""

    @patch("apps.users.services.social_login_services.requests.get")
    @patch("apps.users.services.social_login_services.requests.post")
    def test_duplicate_nickname_gets_suffix(self, mock_post, mock_get) -> None:
        """provider 닉네임이 이미 존재하면 suffix가 붙은 유니크 닉네임으로 생성"""
        # 카카오 닉네임과 동일한 닉네임을 가진 유저를 미리 생성
        create_user(nickname="카카오유저")

        mock_post.return_value = fake_token_response()
        mock_get.return_value = fake_kakao_user_info_response()

        self.client = APIClient()
        response = self.client.get(reverse("kakao-callback"), {"code": "test_code"})

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        # 새로 생성된 유저의 닉네임이 "카카오유저"가 아닌 suffix 포함 닉네임인지 확인
        new_social_user = SocialUser.objects.get(
            provider=SocialProvider.KAKAO, provider_id="123456789"
        )
        self.assertNotEqual(new_social_user.user.nickname, "카카오유저")
