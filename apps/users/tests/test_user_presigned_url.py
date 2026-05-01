from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

if TYPE_CHECKING:
    UserType = Any
else:
    UserType = get_user_model()


class ProfileImagePresignedUrlViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserType.objects.create_user(
            login_id="testuser",
            password="testpassword123",
            name="테스트",
            nickname="테스터",
            gender="M",
        )
        cls.url = reverse("profile-image-presigned-url")
        cls.valid_data = {
            "file_name": "my_profile.png",
            "content_type": "image/png",
        }

    def setUp(self):
        self.client = APIClient()

    # --- 성공 케이스 ---

    @patch("apps.core.utils.s3_handler.boto3.client")
    def test_generate_presigned_url_success(self, mock_boto3_client):
        """인증된 유저가 올바른 요청 시 presigned URL 발급 성공 확인"""
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = (
            "https://oz-pgti.s3.ap-southeast-2.amazonaws.com"
            "/uploads/images/profiles/uuid_my_profile.png?AWSAccessKeyId=..."
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data=self.valid_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("presigned_url", response.data)
        self.assertIn("img_url", response.data)
        self.assertIn("key", response.data)

    @patch("apps.core.utils.s3_handler.boto3.client")
    def test_generate_presigned_url_called_with_correct_args(self, mock_boto3_client):
        """generate_presigned_url이 올바른 인자로 호출되는지 확인"""
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://..."

        self.client.force_authenticate(user=self.user)
        self.client.post(self.url, data=self.valid_data, format="json")

        mock_s3.generate_presigned_url.assert_called_once()

        call_kwargs = mock_s3.generate_presigned_url.call_args
        self.assertEqual(call_kwargs[0][0], "put_object")
        self.assertTrue(
            call_kwargs[1]["Params"]["Key"].startswith("uploads/images/profiles/")
        )
        self.assertTrue(call_kwargs[1]["Params"]["Key"].endswith(".png"))
        self.assertEqual(call_kwargs[1]["Params"]["ContentType"], "image/png")
        self.assertEqual(call_kwargs[1]["ExpiresIn"], 300)

    @patch("apps.core.utils.s3_handler.boto3.client")
    def test_generate_presigned_url_key_format(self, mock_boto3_client):
        """key가 올바른 경로 형식으로 반환되는지 확인"""
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://..."

        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data=self.valid_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["key"].startswith("uploads/images/profiles/"))
        self.assertTrue(response.data["key"].endswith(".png"))

    # --- 실패 케이스 ---

    def test_generate_presigned_url_unauthenticated_fail(self):
        """비인증 유저가 접근 시 401 반환 확인"""
        response = self.client.post(self.url, data=self.valid_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_generate_presigned_url_missing_file_name_fail(self):
        """file_name 누락 시 400 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url, data={"content_type": "image/png"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_generate_presigned_url_missing_content_type_fail(self):
        """content_type 누락 시 400 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url, data={"file_name": "my_profile.png"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_generate_presigned_url_empty_body_fail(self):
        """빈 요청 바디 시 400 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_generate_presigned_url_invalid_extension_fail(self):
        """허용되지 않는 확장자 요청 시 400 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url,
            data={"file_name": "my_profile.gif", "content_type": "image/gif"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_generate_presigned_url_mismatched_content_type_fail(self):
        """확장자와 content_type이 불일치할 때 400 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url,
            data={"file_name": "my_profile.png", "content_type": "image/jpeg"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_method_not_allowed_fail(self):
        """GET 요청 시 405 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ProfileImageUpdateViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserType.objects.create_user(
            login_id="testuser2",
            password="testpassword123",
            name="테스트",
            nickname="테스터2",
            gender="M",
        )
        cls.url = reverse("profile-image-update")
        cls.valid_data = {
            "profile_img_url": "https://oz-pgti.s3.ap-southeast-2.amazonaws.com/uploads/images/profiles/uuid_photo.png",
        }

    def setUp(self):
        self.client = APIClient()

    # --- 성공 케이스 ---

    def test_update_profile_image_success(self):
        """인증된 유저가 올바른 요청 시 프로필 이미지 등록 성공 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.put(self.url, data=self.valid_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "프로필 사진이 등록되었습니다.")

    def test_update_profile_image_saved_to_db(self):
        """프로필 이미지 URL이 DB에 올바르게 저장되는지 확인"""
        self.client.force_authenticate(user=self.user)
        self.client.put(self.url, data=self.valid_data, format="json")

        self.user.refresh_from_db()
        self.assertEqual(self.user.profile_img_url, self.valid_data["profile_img_url"])

    # --- 실패 케이스 ---

    def test_update_profile_image_unauthenticated_fail(self):
        """비인증 유저가 접근 시 401 반환 확인"""
        response = self.client.put(self.url, data=self.valid_data, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_profile_image_missing_profile_img_url_fail(self):
        """profile_img_url 누락 시 400 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.put(self.url, data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_profile_image_invalid_url_fail(self):
        """https로 시작하지 않는 URL 입력 시 400 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.put(
            self.url,
            data={"profile_img_url": "http://invalid-url.com/image.png"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_method_not_allowed_fail(self):
        """GET 요청 시 405 반환 확인"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
