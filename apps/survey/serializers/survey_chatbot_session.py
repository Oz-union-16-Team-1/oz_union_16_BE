from rest_framework import serializers


class SurveyChatbotSessionCreateRequestSerializer(serializers.Serializer):
    """설문 챗봇 세션 시작 요청"""

    is_reset = serializers.BooleanField(
        default=False, help_text="기존 세션 초기화 여부"
    )


class SurveyProgressSerializer(serializers.Serializer):
    """프론트 진행도 표시용 응답"""

    current_step = serializers.IntegerField()
    total_steps = serializers.IntegerField(allow_null=True)
    completion_rate = serializers.FloatField(allow_null=True)


class SurveyChatbotSessionCreateResponseSerializer(serializers.Serializer):
    """설문 챗봇 세션 시작 응답"""

    session_id = serializers.UUIDField()
    status = serializers.CharField()
    ai_question = serializers.CharField()
    progress = SurveyProgressSerializer()
    recommendation_ready = serializers.BooleanField()


class SurveyErrorResponseSerializer(serializers.Serializer):
    """설문 API 에러 응답"""

    detail = serializers.CharField()
