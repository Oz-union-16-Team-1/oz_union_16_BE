from rest_framework import serializers


class PasswordCheckSerializer(serializers.Serializer):
    password = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )
