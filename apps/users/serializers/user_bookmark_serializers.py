from rest_framework import serializers
from apps.users.models import UserLikeBookmark


class UserLikeBookmarkSerializer(serializers.ModelSerializer):
    game_id = serializers.IntegerField(source="game.game_id")
    game_title = serializers.CharField(source="game.name")
    thumbnail_url = serializers.SerializerMethodField()
    genres = serializers.SerializerMethodField()
    liked_at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = UserLikeBookmark
        fields = ["game_id", "game_title", "thumbnail_url", "genres", "liked_at"]

    def get_thumbnail_url(self, obj):
        return obj.game.cover  # cover가 url 문자열이면 그대로, 아니면 가공 필요

    def get_genres(self, obj):
        genres = obj.game.genres  # JSONField: [{id: 1, name: "RPG"}, ...]
        if not genres:
            return []
        # genres JSONField 구조에 따라 조정하세요
        if isinstance(genres[0], dict):
            return [g.get("name", "") for g in genres]
        return genres