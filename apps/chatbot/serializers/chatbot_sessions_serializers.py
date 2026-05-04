from rest_framework import serializers


class ChatbotSessionStatusResponseSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    is_expired = serializers.BooleanField()
    expires_at = serializers.DateTimeField()
    expires_in_seconds = serializers.IntegerField()
    session_ttl_seconds = serializers.IntegerField()
