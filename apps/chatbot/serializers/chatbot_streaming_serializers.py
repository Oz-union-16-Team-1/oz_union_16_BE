from rest_framework import serializers


class ChatbotStreamQuerySerializer(serializers.Serializer):
    session_id = serializers.UUIDField(
        required=True,
        error_messages={
            "required": "session_id는 필수 입력값입니다.",
            "invalid": "session_id 형식이 올바르지 않습니다.",
            "null": "session_id 형식이 올바르지 않습니다.",
        },
    )
