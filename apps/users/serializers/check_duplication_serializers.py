from rest_framework import serializers


class CheckNickNameSerializer(serializers.Serializer):
    nickname = serializers.CharField(
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        }
    )


class CheckIdSerializer(serializers.Serializer):
    login_id = serializers.CharField(
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        }
    )


class CheckResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
