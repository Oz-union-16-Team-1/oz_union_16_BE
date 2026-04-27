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
        # 테스트용 유저 생성
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

    def test_update_password_success(self):
        """비밀번호 변경 성공 및 변경된 비번으로 검증 확인"""
        self.client.force_authenticate(user=self.user)

        data = {
            "old_password": self.password,
            "new_password": "newpassword123!",
            "new_password_check": "newpassword123!",
        }
        response = self.client.post(
            reverse("change-password"), data=data, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 실제 DB에 반영되었는지 check_password로 확인
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpassword123!"))

    def test_update_password_mismatch_fail(self):
        """새 비밀번호 두 개가 다를 때 400 에러 확인"""
        self.client.force_authenticate(user=self.user)

        data = {
            "old_password": self.password,
            "new_password": "newpassword123!",
            "new_password_check": "different123!",
        }
        response = self.client.post(
            reverse("change-password"), data=data, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_password_field_missing_fail(self):
        """비밀번호 필드가 비어있을 때 400 에러 확인"""
        self.client.force_authenticate(user=self.user)

        data = {"old_password": self.password, "new_password_check": "different123!"}
        response = self.client.post(
            reverse("change-password"), data=data, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
