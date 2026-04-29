from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

if TYPE_CHECKING:
    UserType = Any
else:
    UserType = get_user_model()


class UserVerifySocialTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "testpassword123"
        cls.url = reverse("user-social-info")

        cls.naver_user = UserType.objects.create_user(
            login_id="naver_user_123",
            password=cls.password,
            nickname="네이버로그인",
            name="네이버",
        )
        cls.google_user = UserType.objects.create_user(
            login_id="google_tester",
            password=cls.password,
            nickname="구글로그인",
            name="구글",
        )
        cls.admin_keyword_user = UserType.objects.create_user(
            login_id="admin_account",
            password=cls.password,
            nickname="관리자키워드",
            name="관리자",
        )
        cls.normal_user = UserType.objects.create_user(
            login_id="regular_user",
            password=cls.password,
            nickname="일반유저",
            name="일반",
        )

    def setUp(self):
        self.client = APIClient()

    def test_get_social_info_naver_success(self):
        """네이버 아이디로 시작하는 유저의 소셜 정보 조회 성공 테스트"""
        self.client.force_authenticate(user=self.naver_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_social"], True)
        self.assertEqual(response.data["social_type"], "naver")

    def test_get_social_info_google_success(self):
        """구글 아이디로 시작하는 유저의 소셜 정보 조회 성공 테스트"""
        self.client.force_authenticate(user=self.google_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_social"], True)
        self.assertEqual(response.data["social_type"], "google")

    def test_get_social_info_admin_keyword_success(self):
        """admin 키워드로 시작하는 유저의 식별 테스트"""
        self.client.force_authenticate(user=self.admin_keyword_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_social"], True)
        self.assertEqual(response.data["social_type"], "admin")

    def test_get_social_info_normal_user_success(self):
        """키워드에 해당하지 않는 일반 유저 조회 테스트"""
        self.client.force_authenticate(user=self.normal_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["is_social"], False)
        self.assertEqual(response.data["social_type"], "normal")

    def test_get_social_info_unauthenticated_fail(self):
        """로그인하지 않은 상태에서 접근 시 401 에러 확인"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
