from rest_framework import serializers


class GameLikeResponseSerializer(serializers.Serializer):
    game_id = serializers.IntegerField(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
