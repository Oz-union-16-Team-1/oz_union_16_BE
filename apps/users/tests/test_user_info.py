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

    # ---------------------------------------------------------------------------
    # 회원 정보 수정 API
    # ---------------------------------------------------------------------------

    def test_update_my_info_success(self):
        """닉네임과 전화번호 수정 시 성공적으로 반영되는지 확인"""
        self.client.force_authenticate(user=self.user)

        updated_data = {"nickname": "새로운길동", "profile_img_url": "testurl"}

        # PATCH 요청 실행
        response = self.client.patch(self.url, data=updated_data, format="json")

        # 1. 응답 코드 및 데이터 확인
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["nickname"], updated_data["nickname"])
        self.assertEqual(
            response.data["profile_img_url"], updated_data["profile_img_url"]
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "새로운길동")
        self.assertEqual(self.user.profile_img_url, "testurl")

        self.assertIn("nickname", response.data)
        self.assertIn("detail", response.data)

        self.assertNotIn("password", response.data)

    def test_update_my_info_profile_success(self):
        """일부 필드(profile_img_url)만 전송해도 정상적으로 수정되는지 확인 (partial=True 검증)"""
        self.client.force_authenticate(user=self.user)

        updated_data = {"profile_img_url": "testurl12"}
        response = self.client.patch(self.url, data=updated_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(str(self.user.profile_img_url), "testurl12")

    def test_update_my_info_nickname_success(self):
        """일부 필드(nickname)만 전송해도 정상적으로 수정되는지 확인 (partial=True 검증)"""
        self.client.force_authenticate(user=self.user)

        updated_data = {"nickname": "업데이트"}
        response = self.client.patch(self.url, data=updated_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(str(self.user.nickname), "업데이트")

    def test_update_my_info_unauthenticated_fail(self):
        """로그인하지 않은 유저가 수정을 시도하면 401 반환"""
        updated_data = {"nickname": "미인증수정"}
        response = self.client.patch(self.url, data=updated_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_nickname_duplicate_fail(self):
        """이미 다른 유저가 사용 중인 닉네임으로 수정 시도 시 409 반환 확인"""
        other_user_data = {
            "login_id": "otheruser",
            "password": "password123",
            "nickname": "중복닉네임",
            "name": "중복테스트",
            "gender": "M",
        }
        UserType.objects.create_user(**other_user_data)

        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            self.url, data={"nickname": "중복닉네임"}, format="json"
        )

        # 3. 409 에러 확인
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn(
            "중복된 닉네임이 존재합니다.", response.data["error_detail"]["nickname"]
        )
