from django.db import DatabaseError
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

from apps.match.constants import API_GENRE_NAME_MAP
from apps.match.models import MatchGenreImagePublished


class MatchGenreImageCacheUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "이미지 데이터 서비스가 일시적으로 불가합니다."


class MatchGenreImageQueryService:
    def get_genre_image(self, genre_id: int) -> dict[str, object]:
        try:
            row = (
                MatchGenreImagePublished.objects.filter(api_genre_id=genre_id)
                .values("image_url")
                .first()
            )
        except DatabaseError as exc:
            raise MatchGenreImageCacheUnavailable() from exc

        if not row or not row.get("image_url"):
            raise NotFound("해당 장르의 이미지를 찾을 수 없습니다.")

        return {
            "genre_id": genre_id,
            "genre_name": API_GENRE_NAME_MAP[genre_id],
            "image_url": row["image_url"],
        }
