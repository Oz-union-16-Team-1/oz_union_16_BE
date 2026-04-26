from rest_framework import serializers

from apps.users.models import User


class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "login_id",
            "email",
            "name",
            "nickname",
            "gender",
            "profile_img_url",
            "phone_number",
            "birthday",
            "created_at",
        )
        read_only_fields = fields


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("nickname", "profile_img_url")


class UserUpdateResponseSerializer(serializers.Serializer):
    nickname = serializers.CharField()
    profile_img_url = serializers.CharField()
    detail = serializers.CharField(default="회원 정보가 수정되었습니다.")
