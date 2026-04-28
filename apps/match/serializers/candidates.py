from rest_framework import serializers


class MatchCandidatesQuerySerializer(serializers.Serializer):
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
    retry_no = serializers.IntegerField(
        required=False,
        min_value=0,
        error_messages={
            "invalid": "정수 형태로 입력해주세요.",
            "min_value": "retry_no는 0 이상이어야 합니다.",
        },
    )


class MatchCandidateResultSerializer(serializers.Serializer):
    game_id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    trailer_url = serializers.CharField(read_only=True, allow_blank=True)
    is_liked = serializers.BooleanField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    genres = serializers.ListField(child=serializers.CharField(), read_only=True)
    rating = serializers.FloatField(read_only=True)


class MatchCandidatesResponseSerializer(serializers.Serializer):
    genre_id = serializers.IntegerField(read_only=True)
    retry_no = serializers.IntegerField(read_only=True)
    count = serializers.IntegerField(read_only=True)
    results = MatchCandidateResultSerializer(many=True, read_only=True)
