from unittest.mock import patch

from django.db import DatabaseError
from django.test import SimpleTestCase
from rest_framework.exceptions import NotFound

from apps.match.services.genre_image_query import (
    MatchGenreImageCacheUnavailable,
    MatchGenreImageQueryService,
)


class MatchGenreImageQueryServiceTest(SimpleTestCase):
    def setUp(self) -> None:
        self.service = MatchGenreImageQueryService()

    # 게시본 DB에 image_url이 있으면 정상 반환
    @patch("apps.match.services.genre_image_query.MatchGenreImagePublished.objects.filter")
    def test_get_genre_image_success(self, mock_filter):
        mock_filter.return_value.values.return_value.first.return_value = {
            "image_url": "https://example.com/ok.jpg"
        }

        result = self.service.get_genre_image(1)

        self.assertEqual(result["genre_id"], 1)
        self.assertEqual(result["image_url"], "https://example.com/ok.jpg")
        self.assertTrue(result["genre_name"])

    # 게시본이 없거나 image_url 누락이면 404
    @patch("apps.match.services.genre_image_query.MatchGenreImagePublished.objects.filter")
    def test_get_genre_image_not_found(self, mock_filter):
        mock_filter.return_value.values.return_value.first.return_value = None

        with self.assertRaises(NotFound):
            self.service.get_genre_image(1)

    # DB 조회 장애 시 503 예외로 변환
    @patch("apps.match.services.genre_image_query.MatchGenreImagePublished.objects.filter")
    def test_get_genre_image_cache_unavailable(self, mock_filter):
        mock_filter.side_effect = DatabaseError("db down")

        with self.assertRaises(MatchGenreImageCacheUnavailable):
            self.service.get_genre_image(1)
