from rest_framework import serializers

from apps.games.models import Game


class GameBoxSerializer(serializers.ModelSerializer):
    # 명세서에 따라 FloatField로 명시적 선언
    rating = serializers.FloatField(read_only=True)
    total_rating = serializers.FloatField(read_only=True)
    aggregated_rating = serializers.FloatField(read_only=True)

    class Meta:
        model = Game
        fields = "__all__"  # 40개 전체 컬럼 사용

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        # 1. 평점 소수점 처리
        float_fields = ["rating", "total_rating", "aggregated_rating"]
        for field in float_fields:
            if ret.get(field) is not None:
                ret[field] = float(f"{ret[field]:.1f}")

        # 2. Cover 이미지 (이미 ID만 저장되어 있다면 바로 URL 변환)
        if ret.get("cover") and not str(ret["cover"]).startswith("http"):
            ret["cover"] = (
                f"https://images.igdb.com/igdb/image/upload/t_cover_big/{ret['cover']}.jpg"
            )

        # 3. 스크린샷 (서비스에서 이미 ['id1', 'id2'] 형태로 저장했다면)
        if ret.get("screenshots") and isinstance(ret["screenshots"], list):
            new_screenshots = []
            for s in ret["screenshots"]:
                if isinstance(s, str):  # ID 문자열인 경우
                    new_screenshots.append(
                        f"https://images.igdb.com/igdb/image/upload/t_screenshot_med/{s}.jpg"
                    )
                elif isinstance(s, dict) and "image_id" in s:  # 혹시 딕셔너리인 경우
                    new_screenshots.append(
                        f"https://images.igdb.com/igdb/image/upload/t_screenshot_med/{s['image_id']}.jpg"
                    )
            ret["screenshots"] = new_screenshots

        # 4. 누락된 컬럼들 기본값 및 리스트화
        list_fields = [
            "genres",
            "themes",
            "screenshots",
            "videos",
            "game_modes",
            "player_perspectives",
            "keywords",
            "language_supports",
            "franchises",
            "remakes",
            "remasters",
            "expansions",
            "dlcs",
            "multiplayer_modes",
            "involved_companies",
        ]
        for field in list_fields:
            if ret.get(field) is None:
                ret[field] = []

        return ret
