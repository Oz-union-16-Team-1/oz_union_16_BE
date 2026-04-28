from rest_framework import serializers

from apps.core.igdb import IGDB
from apps.games.models import Game


class GameTop100Serializer(serializers.ModelSerializer):
    game_id = serializers.IntegerField(read_only=True)
    rating = serializers.FloatField(read_only=True)
    total_rating = serializers.FloatField(read_only=True)
    total_rating_count = serializers.IntegerField(read_only=True)
    first_release_date = serializers.DateTimeField(format="%Y-%m-%d", read_only=True)

    class Meta:
        model = Game
        fields = [
            "game_id",
            "name",
            "slug",
            "cover",
            "rating",
            "total_rating",
            "total_rating_count",
            "first_release_date",
            "genres",
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        if ret.get("rating") is not None:
            ret["rating"] = round(float(ret["rating"]), 1)
        if ret.get("total_rating") is not None:
            ret["total_rating"] = round(float(ret["total_rating"]), 1)

        if ret.get("genres"):
            ret["genres"] = [
                IGDB.GENRE_NAME_MAP.get(gid, f"기타({gid})") for gid in ret["genres"]
            ]
        cover_id = ret.get("cover")
        if cover_id:
            cover_id_str = str(cover_id)
            # 순서 변경: // 체크를 먼저 수행하여 중복 결합 방지
            if cover_id_str.startswith("//"):
                ret["cover"] = f"https:{cover_id_str}"
            elif not cover_id_str.startswith("http"):
                ret["cover"] = (
                    f"https://images.igdb.com/igdb/image/upload/t_cover_big/{cover_id_str}.jpg"
                )

        return ret
