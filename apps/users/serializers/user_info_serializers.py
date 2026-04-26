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
