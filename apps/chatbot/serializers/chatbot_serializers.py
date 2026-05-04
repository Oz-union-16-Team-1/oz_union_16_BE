from rest_framework import serializers


class ChatbotMessageRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            "required": "메시지는 필수 입력값입니다.",
            "blank": "메시지는 비어 있을 수 없습니다.",
            "null": "메시지는 비어 있을 수 없습니다.",
            "invalid": "메시지 형식이 올바르지 않습니다.",
        },
    )
    session_id = serializers.CharField(
        required=False,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            "blank": "session_id 형식이 올바르지 않습니다.",
            "null": "session_id 형식이 올바르지 않습니다.",
            "invalid": "session_id 형식이 올바르지 않습니다.",
        },
    )

    def validate_message(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("메시지는 2자 이상이어야 합니다.")
        return value


class ChatbotMessageResponseSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField()
    expires_in_seconds = serializers.IntegerField()
    session_ttl_seconds = serializers.IntegerField()


class ChatbotMessageSchemaResponseSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()


class ChatbotErrorResponseSerializer(serializers.Serializer):
    error_detail = serializers.CharField()


class ChatbotSessionStatusResponseSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    is_expired = serializers.BooleanField()
    expires_at = serializers.DateTimeField()
    expires_in_seconds = serializers.IntegerField()
    session_ttl_seconds = serializers.IntegerField()


class ChatbotStreamQuerySerializer(serializers.Serializer):
    session_id = serializers.UUIDField(
        required=True,
        error_messages={
            "required": "session_id는 필수 입력값입니다.",
            "invalid": "session_id 형식이 올바르지 않습니다.",
            "null": "session_id 형식이 올바르지 않습니다.",
        },
    )
