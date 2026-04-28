from rest_framework import serializers


class ProfileImageUpdateSerializer(serializers.Serializer):
    profile_img_url = serializers.URLField(
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        }
    )

    def validate_profile_img_url(self, value: str) -> str:
        if not value.startswith("https://"):
            raise serializers.ValidationError("올바른 이미지 주소 형식이 아닙니다.")
        return value
