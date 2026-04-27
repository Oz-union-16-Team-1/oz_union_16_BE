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


def create_user(**kwargs) -> UserType:
    defaults = {
        "login_id": "testuser1",
        "password": "testpassword123",
        "name": "테스터",
        "nickname": "테스트닉네임",
        "gender": "M",
    }
    defaults.update(kwargs)
    user = UserType.objects.create_user(**defaults)
    return user


class CheckDuplicationTest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.check_id_url = reverse("check-id")
        self.check_nickname_url = reverse("check-nickname")

    # -----------------------------------------------------------------------
    # 아이디 중복 체크 테스트
    # -----------------------------------------------------------------------

    def test_check_id_success(self):
        """사용 가능한 아이디인 경우 200 반환"""
        data = {"login_id": "new_awesome_id"}
        response = self.client.post(self.check_id_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "사용가능한 아이디 입니다.")

    def test_check_id_duplicate_fail(self):
        """이미 존재하는 아이디인 경우 409 반환"""
        existing_id = "duplicate_id"
        create_user(login_id=existing_id)

        data = {"login_id": existing_id}
        response = self.client.post(self.check_id_url, data, format="json")

        # ConflictException이 409를 던지는지 확인
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn(
            "중복된 아이디가 존재합니다.", response.data["error_detail"]["login_id"]
        )

    def test_check_id_missing_field_fail(self):
        """필드 누락 시 400 반환 (Serializer 검증)"""
        data = {}  # login_id 필드 없음
        response = self.client.post(self.check_id_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # -----------------------------------------------------------------------
    # 닉네임 중복 체크 테스트
    # -----------------------------------------------------------------------

    def test_check_nickname_success(self):
        """사용 가능한 닉네임인 경우 200 반환"""
        data = {"nickname": "새로운닉네임"}
        response = self.client.post(self.check_nickname_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "사용가능한 닉네임 입니다.")

    def test_check_nickname_duplicate_fail(self):
        """이미 존재하는 닉네임인 경우 409 반환"""
        existing_nickname = "iam_duplicate"
        create_user(nickname=existing_nickname)

        data = {"nickname": existing_nickname}
        response = self.client.post(self.check_nickname_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn(
            "중복된 닉네임이 존재합니다.", response.data["error_detail"]["nickname"]
        )

    def test_check_nickname_missing_field_fail(self):
        """필드 누락 시 400 반환 (Serializer 검증)"""
        data = {}  # nickname 필드 없음
        response = self.client.post(self.check_nickname_url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
