from rest_framework import serializers


class UserVerifySocialSerializer(serializers.Serializer):
    is_social = serializers.BooleanField(read_only=True)
    social_type = serializers.CharField(read_only=True)
