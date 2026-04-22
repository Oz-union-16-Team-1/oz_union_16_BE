import json

from django.test import SimpleTestCase
from rest_framework.exceptions import NotFound

from apps.match.services.genre_image_query import (
    MatchGenreImageCacheUnavailable,
    MatchGenreImageQueryService,
)
from apps.match.tests.helpers import FakeRedis


class MatchGenreImageQueryServiceTest(SimpleTestCase):
    def setUp(self) -> None:
        self.service = MatchGenreImageQueryService()
        self.service.cache_key = "match:genre:image_map:v1"

    # _parse_image_map은 bytes/json/비정상 입력을 안전하게 dict로 정규화
    def test_parse_image_map_normalizes_input(self):
        parsed = self.service._parse_image_map(
            b'{"1":{"image_url":"https://example.com/a.jpg"}}'
        )
        self.assertIn("1", parsed)

        self.assertEqual(self.service._parse_image_map("not-json"), {})
        self.assertEqual(self.service._parse_image_map("[]"), {})
        self.assertEqual(self.service._parse_image_map(None), {})

    # Redis 캐시에 정상 데이터가 있으면 genre_id/genre_name/image_url을 반환
    def test_get_genre_image_success(self):
        payload = json.dumps({"1": {"image_url": "https://example.com/ok.jpg"}})
        fake_redis = FakeRedis()
        fake_redis.store[self.service.cache_key] = payload
        self.service.redis = fake_redis

        result = self.service.get_genre_image(1)

        self.assertEqual(result["genre_id"], 1)
        self.assertEqual(result["image_url"], "https://example.com/ok.jpg")
        self.assertTrue(result["genre_name"])

    # 캐시에 장르 데이터가 없거나 image_url 누락이면 404(NotFound)를 반환
    def test_get_genre_image_not_found(self):
        fake_redis = FakeRedis()
        fake_redis.store[self.service.cache_key] = json.dumps({"1": {"game_id": 10}})
        self.service.redis = fake_redis

        with self.assertRaises(NotFound):
            self.service.get_genre_image(1)

    # Redis 조회 예외 발생 시 503(MatchGenreImageCacheUnavailable)로 변환
    def test_get_genre_image_cache_unavailable(self):
        fake_redis = FakeRedis()
        fake_redis.raise_error = True
        self.service.redis = fake_redis

        with self.assertRaises(MatchGenreImageCacheUnavailable):
            self.service.get_genre_image(1)
