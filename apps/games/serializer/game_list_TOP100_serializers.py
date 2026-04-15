from rest_framework import serializers


# Game_List_TOP100 API
class GameListTop100Serializer(serializers.Serializer):
    game_id = serializers.IntegerField(source="id")
    name = serializers.CharField()
    # 장르 리스트 추출
    genres = serializers.SerializerMethodField()
    # 목록용 최적화 썸네일 URL
    thumbnail_url = serializers.SerializerMethodField()
    # 평점
    rating = serializers.SerializerMethodField()

    def get_genres(self, obj):
        genre_list = [g.get("name") for g in obj.get("genres", []) if g.get("name")]
        return genre_list if genre_list else ["N/A"]

    def get_thumbnail_url(self, obj):
        cover = obj.get("cover")
        if cover and "url" in cover:
            url = f"https:{cover['url']}"
            return url.replace("t_thumb", "t_cover_big")
        return "N/A"

    def get_rating(self, obj):
        rating = obj.get("rating")
        if rating:
            return round(rating / 10, 1)
        return "N/A"