from rest_framework import serializers


class ChatbotMessageRequestSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
    )
    session_id = serializers.IntegerField(required=False, min_value=1)

    def validate_message(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                "메시지는 공백일 수 없고 2자 이상이어야 합니다."
            )
        return value


class ChatbotMessageResponseSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(min_value=1)


class ChatbotStreamQuerySerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=True, min_value=1)