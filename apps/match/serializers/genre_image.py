from rest_framework import serializers


class MatchGenreImageQuerySerializer(serializers.Serializer):
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


class MatchGenreImageResponseSerializer(serializers.Serializer):
    genre_id = serializers.IntegerField(read_only=True)
    genre_name = serializers.CharField(read_only=True)
    image_url = serializers.URLField(read_only=True)
