import uuid
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

if TYPE_CHECKING:
    UserType = Any
else:
    UserType = get_user_model()
# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------


def make_login_id() -> str:
    return f"user_{uuid.uuid4().hex[:4]}"


def make_nickname() -> str:
    return f"nick_{uuid.uuid4().hex[:4]}"


def create_user(**kwargs) -> UserType:
    """테스트용 유저 생성 헬퍼. 기본값을 제공하고 kwargs로 덮어씁니다.
    password_check는 User 모델에 없는 필드이므로 반드시 제거합니다.
    """
    defaults = {
        "login_id": make_login_id(),
        "password": "testpassword123",
        "name": "홍길동",
        "nickname": make_nickname(),
        "gender": "M",
    }
    defaults.update(kwargs)
    # User 모델에 존재하지 않는 필드 제거
    defaults.pop("password_check", None)
    password = defaults.pop("password")
    user = UserType(**defaults)
    user.set_password(password)
    user.save()
    return user


# ---------------------------------------------------------------------------
# 회원가입
# ---------------------------------------------------------------------------


class SignUpTest(TestCase):
    url: str
    user_data: dict[str, Any]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("signup")

    def setUp(self) -> None:
        self.client = APIClient()
        self.user_data = {
            "login_id": make_login_id(),
            "password": "testpassword123",
            "password_check": "testpassword123",
            "nickname": make_nickname(),
            "name": "홍길동",
            "gender": "M",
        }

    # --- 성공 ---

    def test_signup_success(self) -> None:
        """정상 데이터로 회원가입 시 201 반환 및 유저 생성 확인"""
        response = self.client.post(self.url, self.user_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["detail"], "회원가입이 완료되었습니다.")
        self.assertTrue(
            UserType.objects.filter(login_id=self.user_data["login_id"]).exists()
        )

    # --- 400: 필드 누락 / 형식 오류 ---

    def test_signup_missing_name_fail(self) -> None:
        """필수 필드(name) 누락 시 400"""
        data = self.user_data.copy()
        data.pop("name")

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data["error_detail"])

    def test_signup_missing_login_id_fail(self) -> None:
        """필수 필드(login_id) 누락 시 400"""
        data = self.user_data.copy()
        data.pop("login_id")

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("login_id", response.data["error_detail"])

    def test_signup_short_password_fail(self) -> None:
        """비밀번호 8자 미만 시 400"""
        data = self.user_data.copy()
        data["password"] = "short"
        data["password_check"] = "short"

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data["error_detail"])

    def test_signup_password_mismatch_fail(self) -> None:
        """password / password_check 불일치 시 400"""
        data = self.user_data.copy()
        data["password_check"] = "differentpassword"

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_check", response.data["error_detail"])

    def test_signup_invalid_gender_fail(self) -> None:
        """허용되지 않는 gender 값 입력 시 400"""
        data = self.user_data.copy()
        data["gender"] = "X"

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("gender", response.data["error_detail"])

    # --- 409: 중복 ---

    def test_signup_duplicate_login_id_fail(self) -> None:
        """login_id 중복 시 409"""
        existing_login_id = make_login_id()
        # create_user 헬퍼 사용 - password_check는 내부에서 자동 제거됨
        create_user(login_id=existing_login_id)

        data = self.user_data.copy()
        data["login_id"] = existing_login_id

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("login_id", response.data["error_detail"])
        self.assertIn(
            "이미 중복된 회원가입 내역이 존재합니다.",
            response.data["error_detail"]["login_id"],
        )

    def test_signup_duplicate_nickname_fail(self) -> None:
        """nickname 중복 시 409"""
        existing_nickname = make_nickname()
        create_user(nickname=existing_nickname)

        data = self.user_data.copy()
        data["nickname"] = existing_nickname

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("nickname", response.data["error_detail"])
        self.assertIn(
            "이미 중복된 닉네임이 존재합니다.",
            response.data["error_detail"]["nickname"],
        )


# ---------------------------------------------------------------------------
# 로그인
# ---------------------------------------------------------------------------


class LoginTest(TestCase):
    login_id: str
    password: str
    user: UserType
    url: str

    @classmethod
    def setUpTestData(cls) -> None:
        cls.login_id = make_login_id()
        cls.password = "testpassword123"
        cls.user = create_user(login_id=cls.login_id, password=cls.password)
        cls.url = reverse("login")

    def setUp(self) -> None:
        self.client = APIClient()

    # --- 성공 ---

    def test_login_success(self) -> None:
        """정상 로그인 시 200, access_token JSON 반환 및 refresh_token 쿠키 설정 확인"""
        data = {"login_id": self.login_id, "password": self.password}
        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Access Token은 JSON body에
        self.assertIn("access_token", response.data)
        # Refresh Token은 body에 없고 쿠키에만
        self.assertNotIn("refresh_token", response.data)
        self.assertIn("refresh_token", response.cookies)
        # HttpOnly 속성 확인
        self.assertTrue(response.cookies["refresh_token"]["httponly"])

    # --- 400: 필드 누락 ---

    def test_login_missing_password_fail(self) -> None:
        """password 필드 누락 시 400"""
        data = {"login_id": self.login_id}
        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data["error_detail"])

    def test_login_missing_login_id_fail(self) -> None:
        """login_id 필드 누락 시 400"""
        data = {"password": self.password}
        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("login_id", response.data["error_detail"])

    # --- 401: 인증 실패 ---

    def test_login_wrong_password_fail(self) -> None:
        """비밀번호 불일치 시 401"""
        data = {"login_id": self.login_id, "password": "wrongpassword"}
        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data["error_detail"],
            "로그인 아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    def test_login_nonexistent_user_fail(self) -> None:
        """존재하지 않는 login_id로 시도 시 401"""
        data = {"login_id": "no_such_user", "password": self.password}
        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data["error_detail"],
            "로그인 아이디 또는 비밀번호가 올바르지 않습니다.",
        )

    # --- 403: 차단 계정 ---

    def test_login_inactive_user_fail(self) -> None:
        """비활성(차단) 계정 로그인 시 403"""
        inactive_user = create_user(is_active=False)

        data = {"login_id": inactive_user.login_id, "password": "testpassword123"}
        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error_detail"], "차단된 계정입니다.")


# ---------------------------------------------------------------------------
# 로그아웃
# ---------------------------------------------------------------------------


class LogoutTest(TestCase):
    user: UserType
    url: str

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = create_user()
        cls.url = reverse("logout")

    def setUp(self) -> None:
        self.client = APIClient()

    # --- 성공 ---

    def test_logout_success(self) -> None:
        """유효한 Refresh Token 쿠키로 로그아웃 시 200, 쿠키 삭제 확인"""
        self.client.force_authenticate(user=self.user)
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies["refresh_token"] = str(refresh)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "로그아웃 되었습니다.")
        # 쿠키가 빈 값 + max-age=0 으로 삭제됐는지 확인
        refresh_cookie = response.cookies.get("refresh_token")
        self.assertIsNotNone(refresh_cookie)
        self.assertEqual(refresh_cookie.value, "")
        self.assertEqual(refresh_cookie["max-age"], 0)

    def test_logout_blacklisted_token_fail(self) -> None:
        """이미 블랙리스트에 등록된 토큰으로 로그아웃 시 403"""
        self.client.force_authenticate(user=self.user)
        refresh = RefreshToken.for_user(self.user)
        refresh.blacklist()
        self.client.cookies["refresh_token"] = str(refresh)

        response = self.client.post(self.url)

        # service에서 str ValidationError("인증 정보가 유효하지 않거나 만료되었습니다.") raise
        # → custom_exception_handler → {"error_detail": str}
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["error_detail"],
            "인증 정보가 유효하지 않거나 만료되었습니다.",
        )

    def test_logout_invalid_token_fail(self) -> None:
        """유효하지 않은 토큰 쿠키로 로그아웃 시 403"""
        self.client.force_authenticate(user=self.user)
        self.client.cookies["refresh_token"] = "this-is-not-a-valid-token"

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["error_detail"],
            "인증 정보가 유효하지 않거나 만료되었습니다.",
        )

    def test_logout_no_cookie_fail(self) -> None:
        """refresh_token 쿠키 없이 로그아웃 요청 시 401"""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url)

        # service에서 str ValidationError("로그인 세션이 만료되었습니다.") raise
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data["error_detail"],
            "자격 인증 데이터가 제공되지 않았습니다.",
        )

    # --- 401: 비로그인 ---

    def test_logout_unauthenticated_fail(self) -> None:
        """인증 없이 로그아웃 요청 시 401"""
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# 토큰 재발급
# ---------------------------------------------------------------------------


class TokenRefreshTest(TestCase):
    user: UserType
    url: str

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = create_user()
        cls.url = reverse("token-refresh")

    def setUp(self) -> None:
        self.client = APIClient()

    # --- 성공 ---

    def test_token_refresh_success(self) -> None:
        """유효한 Refresh Token으로 재발급 시 200, 새 access_token 반환 및 새 refresh_token 쿠키 설정 확인"""
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies["refresh_token"] = str(refresh)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Access Token은 body에
        self.assertIn("access_token", response.data)
        # Refresh Token은 body에 없고 쿠키로만
        self.assertNotIn("refresh_token", response.data)
        self.assertIn("refresh_token", response.cookies)
        # 새로 발급된 토큰이 기존과 다른지 확인
        self.assertNotEqual(response.cookies["refresh_token"].value, str(refresh))

    def test_token_refresh_old_token_blacklisted(self) -> None:
        """재발급 후 구 Refresh Token은 블랙리스트에 등록되어 재사용 불가 확인"""
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies["refresh_token"] = str(refresh)
        self.client.post(self.url)

        # 구 토큰으로 재시도
        self.client.cookies["refresh_token"] = str(refresh)
        response = self.client.post(self.url)

        # service에서 str ValidationError("로그인 세션이 만료되었습니다.") raise
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["error_detail"],
            "인증 정보가 유효하지 않거나 만료되었습니다.",
        )

    # --- 400: 쿠키 없음 / 유효하지 않은 토큰 ---

    def test_token_refresh_no_cookie_fail(self) -> None:
        """쿠키 없이 재발급 요청 시 401"""
        response = self.client.post(self.url)

        # service에서 str AuthenticationFailed("자격 인증 데이터가 제공되지 않았습니다.") raise
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.data["error_detail"],
            "자격 인증 데이터가 제공되지 않았습니다.",
        )

    def test_token_refresh_invalid_token_fail(self) -> None:
        """위조된 토큰으로 재발급 시 403"""
        self.client.cookies["refresh_token"] = "totally-fake-token"

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["error_detail"],
            "인증 정보가 유효하지 않거나 만료되었습니다.",
        )

    def test_token_refresh_blacklisted_token_fail(self) -> None:
        """이미 블랙리스트에 등록된 토큰으로 재발급 시 403"""
        refresh = RefreshToken.for_user(self.user)
        refresh.blacklist()
        self.client.cookies["refresh_token"] = str(refresh)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data["error_detail"],
            "인증 정보가 유효하지 않거나 만료되었습니다.",
        )
