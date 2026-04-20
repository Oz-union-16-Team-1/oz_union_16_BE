from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.choices import GenderChoices

User = get_user_model()


class SignUpSerializer(serializers.Serializer):
    login_id = serializers.CharField(max_length=15)
    password = serializers.CharField(write_only=True, min_length=8)
    password_check = serializers.CharField(write_only=True)
    nickname = serializers.CharField(max_length=10)
    name = serializers.CharField(max_length=30)
    gender = serializers.ChoiceField(choices=GenderChoices.choices)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_check"]:
            raise serializers.ValidationError({"password_check": "비밀번호와 일치하지 않습니다."})
        return attrs


class LoginSerializer(serializers.Serializer):
    login_id = serializers.CharField()
    password = serializers.CharField(write_only=True)
