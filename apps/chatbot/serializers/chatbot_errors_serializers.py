from rest_framework import serializers


class ChatbotErrorResponseSerializer(serializers.Serializer):
    error_detail = serializers.CharField()
