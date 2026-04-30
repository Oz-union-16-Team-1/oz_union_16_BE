from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.test import APIClient

from apps.match.services.genre_image_query import MatchGenreImageCacheUnavailable


class MatchGenreImageAPITest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.url = reverse("match-genres-image-url")
        cls.user = get_user_model().objects.create_user(
            login_id="genre_api_user",
            password="Pass1234!",
            name="테스터",
            nickname="genre_tester",
            gender="M",
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("apps.match.views.genre_image.MatchGenreImageQueryService.get_genre_image")
    # 인증된 사용자가 유효한 genre_id 요청 시 200과 이미지 정보를 반환
    def test_get_genre_image_success(self, mock_get_genre_image):
        mock_get_genre_image.return_value = {
            "genre_id": 5,
            "genre_name": "스포츠/레이싱",
            "image_url": "https://images.igdb.com/igdb/image/upload/t_1080p/abc123.jpg",
        }

        response = self.client.get(self.url, {"genre_id": 5})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["genre_id"], 5)
        self.assertIn("image_url", response.data)

    # 비회원 요청은 401을 반환
    def test_get_genre_image_unauthorized_returns_401(self):
        anonymous_client = APIClient()
        response = anonymous_client.get(self.url, {"genre_id": 5})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error_detail", response.data)

    # genre_id가 범위를 벗어나거나 정수 형식이 아니면 400을 반환
    def test_get_genre_image_invalid_genre_id_returns_400(self):
        for invalid in [99, "abc"]:
            with self.subTest(genre_id=invalid):
                response = self.client.get(self.url, {"genre_id": invalid})
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("genre_id", response.data["error_detail"])

    @patch("apps.match.views.genre_image.MatchGenreImageQueryService.get_genre_image")
    # 유효한 genre_id라도 캐시에 해당 장르 이미지가 없으면 404를 반환
    def test_get_genre_image_not_found_returns_404(self, mock_get_genre_image):
        mock_get_genre_image.side_effect = NotFound(
            "해당 장르의 이미지를 찾을 수 없습니다."
        )

        response = self.client.get(self.url, {"genre_id": 1})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["error_detail"], "해당 장르의 이미지를 찾을 수 없습니다."
        )

    @patch("apps.match.views.genre_image.MatchGenreImageQueryService.get_genre_image")
    # 캐시 조회 과정에서 장애가 발생하면 503을 반환
    def test_get_genre_image_cache_unavailable_returns_503(self, mock_get_genre_image):
        mock_get_genre_image.side_effect = MatchGenreImageCacheUnavailable()

        response = self.client.get(self.url, {"genre_id": 1})

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.data["error_detail"], "이미지 데이터 서비스가 일시적으로 불가합니다."
        )
