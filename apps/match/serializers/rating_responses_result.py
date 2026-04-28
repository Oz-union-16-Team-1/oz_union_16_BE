from rest_framework import serializers


class MatchResponsesResultQuerySerializer(serializers.Serializer):
    genre_id = serializers.IntegerField(
        required=True,
        min_value=1,
        max_value=8,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "null": "이 필드는 필수 항목입니다.",
            "invalid": "정수 형태로 입력해주세요.",
            "min_value": "유효하지 않은 genre_id 입니다.",
            "max_value": "유효하지 않은 genre_id 입니다.",
        },
    )
    cursor = serializers.CharField(required=False)
    page_size = serializers.IntegerField(
        required=False,
        default=5,
        min_value=1,
        max_value=15,
        error_messages={
            "invalid": "정수 형태로 입력해주세요.",
            "min_value": "page_size는 1 이상이어야 합니다.",
            "max_value": "page_size는 15 이하여야 합니다.",
        },
    )


class MatchResponsesResultItemSerializer(serializers.Serializer):
    game_id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    genres = serializers.ListField(child=serializers.CharField(), read_only=True)
    thumbnail_url = serializers.CharField(read_only=True, allow_blank=True)
    rating = serializers.FloatField(read_only=True, help_text="게임 평점 (0~100)")
    is_liked = serializers.BooleanField(read_only=True)


class MatchResponsesResultResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(read_only=True)
    count = serializers.IntegerField(read_only=True)
    next = serializers.CharField(read_only=True, allow_null=True)
    results = MatchResponsesResultItemSerializer(many=True, read_only=True)
