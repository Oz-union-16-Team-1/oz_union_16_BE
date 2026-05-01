from rest_framework import serializers

from apps.core.igdb import IGDB
from apps.games.models import Game

# IGDB 장르 ID → 한국어 이름 매핑 (igdb.py의 GENRE_NAME_MAP 활용)
GENRE_NAME_MAP: dict[int, str] = IGDB.GENRE_NAME_MAP


class GameTop100Serializer(serializers.ModelSerializer):
    """
    명세서 23라인: 인기 TOP 100 게임 리스트 조회를 위한 시리얼라이저
    """

    name = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = [
            "game_id",
            "name",
            "genres",
            "thumbnail_url",
            "rating",
            "is_liked",
            "like_count",
        ]

    def get_name(self, obj: Game) -> str | None:
        original_name = self._clean_string(obj.name)
        if original_name is None:
            return None

        korean_name = self._clean_string(obj.name_ko)
        if korean_name and korean_name.casefold() != original_name.casefold():
            return f"{korean_name} ({original_name})"

        return original_name

    def get_genres(self, obj: Game) -> list[str]:
        """
        DB에 저장된 장르 ID 리스트를 한국어 장르명 리스트로 변환합니다.
        """
        genre_ids: list[int] = obj.genres or []
        return [
            GENRE_NAME_MAP.get(gid, "기타")
            for gid in genre_ids
            if gid in GENRE_NAME_MAP
        ]

    def get_thumbnail_url(self, obj: Game) -> str | None:
        if obj.cover:
            return f"https://images.igdb.com/igdb/image/upload/t_720p/{obj.cover}.jpg"
        return None

    def get_rating(self, obj: Game) -> float:
        val = obj.total_rating
        if val is None:
            return 0.0
        try:
            return round(float(val), 1)
        except ValueError:
            return 0.0

    def get_is_liked(self, obj: Game) -> bool:
        liked_game_ids: set[int] = self.context.get("liked_game_ids", set())
        return obj.game_id in liked_game_ids

    def to_representation(self, instance: Game) -> dict:
        ret = super().to_representation(instance)
        if ret.get("rating") is None:
            ret["rating"] = 0.0
        return ret

    @staticmethod
    def _clean_string(value: str | None) -> str | None:
        if not isinstance(value, str):
            return None

        stripped = value.strip()
        return stripped or None


class GameTop100ListResponseSerializer(serializers.Serializer):
    ranked_at = serializers.DateTimeField()
    count = serializers.IntegerField()
    next = serializers.IntegerField(allow_null=True)
    results = GameTop100Serializer(many=True)
