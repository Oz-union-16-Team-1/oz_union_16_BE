# apps/games/serializer/game_list_top100_serializers.py
from rest_framework import serializers

from apps.games.models import Game


class GameTop100Serializer(serializers.ModelSerializer):
    game_id = serializers.IntegerField(read_only=True)
    rating = serializers.FloatField(read_only=True)
    total_rating = serializers.FloatField(read_only=True)
    total_rating_count = serializers.IntegerField(read_only=True)
    first_release_date = serializers.DateTimeField(format="%Y-%m-%d", read_only=True)

    GENRE_NAME_MAP = {
        1: "액션",
        2: "포인트 앤 클릭",
        4: "격투",
        5: "슈팅",
        7: "음악",
        8: "플랫폼",
        9: "퍼즐",
        10: "레이싱",
        11: "실시간 전략(RTS)",
        12: "역할수행(RPG)",
        13: "시뮬레이션",
        14: "스포츠",
        15: "전략",
        16: "턴제 전략(TBS)",
        24: "전술",
        25: "핵 앤 슬래시",
        26: "퀴즈/상식",
        30: "핀볼",
        31: "어드벤처",
        32: "인디",
        33: "아케이드",
        34: "비주얼 노벨",
        35: "카드 및 보드 게임",
        36: "모바(MOBA)",
    }

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
                self.GENRE_NAME_MAP[gid]
                for gid in ret["genres"]
                if gid in self.GENRE_NAME_MAP
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
