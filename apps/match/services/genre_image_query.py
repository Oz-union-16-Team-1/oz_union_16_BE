import json

from django.conf import settings
from redis import Redis
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from apps.match.constants import API_GENRE_NAME_MAP


class MatchGenreImageCacheUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "이미지 캐시 서비스가 일시적으로 불가합니다."


class MatchGenreImageQueryService:
    def __init__(self) -> None:
        self.redis = Redis.from_url(
            settings.MATCH_REDIS_URL,
            decode_responses=True,
            socket_timeout=settings.MATCH_GENRE_IMAGE_QUERY_TIMEOUT,
        )
        self.cache_key = settings.MATCH_GENRE_IMAGE_CACHE_KEY

    def get_genre_image(self, genre_id: int) -> dict:
        try:
            raw = self.redis.get(self.cache_key)
            image_map = json.loads(raw) if raw else {}
        except Exception as exc:
            raise MatchGenreImageCacheUnavailable() from exc

        item = image_map.get(str(genre_id))
        if not isinstance(item, dict) or not item.get("image_url"):
            raise NotFound("해당 장르의 이미지를 찾을 수 없습니다.")

        return {
            "genre_id": genre_id,
            "genre_name": API_GENRE_NAME_MAP[genre_id],
            "image_url": item["image_url"],
        }
