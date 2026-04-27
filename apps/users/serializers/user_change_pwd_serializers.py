from rest_framework import serializers


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        required=True,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )
    new_password = serializers.CharField(
        required=True,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )
    new_password_check = serializers.CharField(
        required=True,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_check"]:
            raise serializers.ValidationError(
                {"new_password_check": "비밀번호와 일치하지 않습니다."}
            )
        return attrs
