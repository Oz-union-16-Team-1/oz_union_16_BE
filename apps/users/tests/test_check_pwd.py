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


class MyInfoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = "testpassword123"
        cls.user_data = {
            "login_id": "testuser123",
            "password": "testpassword123",
            "name": "홍길동",
            "nickname": "길동이",
            "email": "test@example.com",
            "gender": "M",
            "birthday": "1990-01-01",
        }
        cls.user = UserType.objects.create_user(**cls.user_data)
        cls.url = reverse("user-info")  # urls.py의 name 확인

    def setUp(self):
        self.client = APIClient()


    def test_password_check_success(self):
        """비밀번호 확인 API 성공 테스트"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            reverse("check-password"), data={"password": self.password}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


    def test_password_check_fail(self):
        """비밀번호 확인 API 실패 테스트"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("check-password"), data={"password": "wrong"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
