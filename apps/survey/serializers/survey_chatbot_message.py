from rest_framework import serializers

from apps.survey.serializers.survey_chatbot_session import SurveyProgressSerializer


class SurveyChatbotMessageRequestSerializer(serializers.Serializer):
    """설문 챗봇 메시지 진행 요청"""

    message = serializers.CharField(help_text="사용자 답변", trim_whitespace=True)


class SurveyChatbotMessageResponseSerializer(serializers.Serializer):
    """설문 챗봇 메시지 진행 응답"""

    session_id = serializers.UUIDField()
    status = serializers.CharField()
    warning_message = serializers.CharField(allow_null=True, required=False)
    ai_message = serializers.CharField(allow_null=True)
    progress = SurveyProgressSerializer()
    recommendation_ready = serializers.BooleanField()
    survey_answer = serializers.CharField(allow_null=True, required=False)
    excluded_keywords = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=True,
        required=False,
    )


class SurveyChatbotMessageErrorResponseSerializer(serializers.Serializer):
    """설문 챗봇 메시지 에러 응답"""

    error_detail = serializers.CharField()


class SurveyChatbotMessageLockedResponseSerializer(serializers.Serializer):
    """설문 챗봇 메시지 잠금 에러 응답"""

    error_detail = serializers.CharField()
    retry_after_seconds = serializers.IntegerField()
