from rest_framework import serializers


class MatchResponseItemSerializer(serializers.Serializer):
    game_id = serializers.IntegerField(
        required=True,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "null": "이 필드는 필수 항목입니다.",
            "invalid": "정수 형태로 입력해주세요.",
        },
    )
    rating = serializers.IntegerField(
        required=True,
        min_value=1,
        max_value=5,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "null": "이 필드는 필수 항목입니다.",
            "invalid": "정수 형태로 입력해주세요.",
            "min_value": "1~5 사이 정수여야 합니다.",
            "max_value": "1~5 사이 정수여야 합니다.",
        },
    )
    is_liked = serializers.BooleanField(required=False)


class MatchResponsesRequestSerializer(serializers.Serializer):
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
        default=0,
        min_value=0,
        error_messages={
            "invalid": "정수 형태로 입력해주세요.",
            "min_value": "retry_no는 0 이상이어야 합니다.",
        },
    )
    candidate_date = serializers.DateField(required=False)
    match_result = MatchResponseItemSerializer(many=True, min_length=1, max_length=5)


class MatchResponseResultSerializer(serializers.Serializer):
    game_id = serializers.IntegerField(read_only=True)
    rating = serializers.IntegerField(read_only=True)
    is_liked = serializers.BooleanField(read_only=True)


class MatchResponsesResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(read_only=True)
    match_result = MatchResponseResultSerializer(many=True, read_only=True)
