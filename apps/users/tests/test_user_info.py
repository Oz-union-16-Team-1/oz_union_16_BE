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

    # --- 성공 케이스 ---

    def test_get_my_info_success(self):
        """인증된 사용자가 자신의 정보를 조회할 때 200 OK와 올바른 데이터를 반환하는지 확인"""
        # 강제 인증 (Login 상태 시뮬레이션)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["login_id"], self.user_data["login_id"])
        self.assertEqual(response.data["nickname"], self.user_data["nickname"])
        self.assertEqual(response.data["email"], self.user_data["email"])

        # 보안 확인: 응답 데이터에 password 필드가 절대 없어야 함
        self.assertNotIn("password", response.data)

    # --- 실패 케이스 ---

    def test_get_my_info_unauthenticated_fail(self):
        """로그인하지 않은 사용자가 접근 시 401 Unauthorized 반환 확인"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_post_method_not_allowed_fail(self):
        """GET 전용 API에 POST 요청을 보낼 경우 405 Method Not Allowed 반환 확인"""
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url, data={})

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_info_is_read_only(self):
        """UserInfoSerializer가 모든 필드를 read_only로 처리하는지 간접 확인"""
        self.client.force_authenticate(user=self.user)

        new_nickname = "해커닉네임"
        response = self.client.patch(self.url, {"nickname": new_nickname})

        self.user.refresh_from_db()
        self.assertNotEqual(self.user.nickname, new_nickname)
