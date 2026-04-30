from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.users.choices import SocialProvider
from apps.users.models import SocialUser

if TYPE_CHECKING:
    UserType = Any
else:
    UserType = get_user_model()


class UserVerifySocialTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "testpassword123"
        cls.url = reverse("user-social-info")

        # 네이버 소셜 유저 — SocialUser 레코드까지 생성
        cls.naver_user = UserType.objects.create_user(
            login_id="naver_abc1234567",
            password=cls.password,
            nickname="네이버로그인",
            name="네이버",
        )
        SocialUser.objects.create(
            provider=SocialProvider.NAVER,
            provider_id="naver_provider_001",
            user=cls.naver_user,
        )

        # 구글 소셜 유저 — SocialUser 레코드까지 생성
        cls.google_user = UserType.objects.create_user(
            login_id="google_abc1234567",
            password=cls.password,
            nickname="구글로그인",
            name="구글",
        )
        SocialUser.objects.create(
            provider=SocialProvider.GOOGLE,
            provider_id="google_provider_001",
            user=cls.google_user,
        )

        # 관리자 계정 — is_staff=True 로 판별
        cls.admin_user = UserType.objects.create_user(
            login_id="admin_account",
            password=cls.password,
            nickname="관리자",
            name="관리자",
            is_staff=True,
        )

        # 일반 유저 — SocialUser 없음, is_staff=False
        cls.normal_user = UserType.objects.create_user(
            login_id="regular_user",
            password=cls.password,
            nickname="일반유저",
            name="일반",
        )

    def setUp(self):
        self.client = APIClient()

    def test_get_social_info_naver_success(self):
        """네이버 SocialUser가 등록된 유저의 소셜 정보 조회 성공 테스트"""
        self.client.force_authenticate(user=self.naver_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_social"], True)
        self.assertEqual(response.data["social_type"], SocialProvider.NAVER)

    def test_get_social_info_google_success(self):
        """구글 SocialUser가 등록된 유저의 소셜 정보 조회 성공 테스트"""
        self.client.force_authenticate(user=self.google_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_social"], True)
        self.assertEqual(response.data["social_type"], SocialProvider.GOOGLE)

    def test_get_social_info_admin_success(self):
        """is_staff=True인 관리자 계정 판별 테스트"""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_social"], True)
        self.assertEqual(response.data["social_type"], "admin")

    def test_get_social_info_normal_user_success(self):
        """SocialUser 없고 is_staff=False인 일반 유저 조회 테스트"""
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_social"], False)
        self.assertEqual(response.data["social_type"], "normal")

    def test_get_social_info_unauthenticated_fail(self):
        """로그인하지 않은 상태에서 접근 시 401 에러 확인"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)