from rest_framework import serializers

from apps.users.choices import GenderChoices


class SignUpSerializer(serializers.Serializer):
    login_id = serializers.CharField(
        max_length=15,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
            "min_length": "비밀번호는 8자 이상이어야 합니다.",
        },
    )
    password_check = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )
    nickname = serializers.CharField(
        max_length=10,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )
    name = serializers.CharField(
        max_length=30,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )
    gender = serializers.ChoiceField(
        choices=GenderChoices.choices,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "invalid_choice": "올바른 성별 값을 입력해주세요.",
        },
    )

    def validate_login_id(self, value):
        forbidden_keywords = ["naver", "google", "kakao", "admin"]

        lower_value = value.lower()

        for keyword in forbidden_keywords:
            if keyword in lower_value:
                raise serializers.ValidationError(
                    f"'{keyword}'가 포함된 아이디는 사용할 수 없습니다."
                )

        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_check"]:
            raise serializers.ValidationError(
                {"password_check": "비밀번호와 일치하지 않습니다."}
            )
        return attrs


class LoginSerializer(serializers.Serializer):
    login_id = serializers.CharField(
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        }
    )
    password = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        },
    )
