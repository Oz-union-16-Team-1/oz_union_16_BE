from rest_framework import serializers


class PresignedUrlRequestSerializer(serializers.Serializer):
    file_name = serializers.CharField(
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        }
    )
    content_type = serializers.CharField(
        error_messages={
            "required": "이 필드는 필수 항목입니다.",
            "blank": "이 필드는 필수 항목입니다.",
        }
    )


class PresignedUrlResponseSerializer(serializers.Serializer):
    presigned_url = serializers.CharField()
    img_url = serializers.CharField()
    key = serializers.CharField()
