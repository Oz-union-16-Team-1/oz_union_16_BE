from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.survey.serializers.survey_chatbot_session import (
    SurveyChatbotSessionCreateRequestSerializer,
    SurveyChatbotSessionCreateResponseSerializer,
    SurveyChatbotSessionResetResponseSerializer,
    SurveyErrorResponseSerializer,
)
from apps.survey.services.survey_chatbot_session import SurveyChatbotSessionService


class SurveyChatbotSessionCreateAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SurveyChatbotSessionCreateRequestSerializer

    @extend_schema(
        tags=["survey"],
        summary="설문 챗봇 세션 시작",
        description="유저별 설문 챗봇 세션을 생성하거나 기존 세션을 반환하고 첫 질문을 제공합니다.",
        request=SurveyChatbotSessionCreateRequestSerializer,
        responses={
            201: SurveyChatbotSessionCreateResponseSerializer,
            401: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="인증 정보가 없거나 유효하지 않은 경우",
                examples=[
                    OpenApiExample(
                        "Unauthorized",
                        value={
                            "detail": "자격 인증데이터(authentication credentials)가 제공되지 않았습니다."
                        },
                    )
                ],
            ),
            503: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="LLM 첫 질문 생성에 실패한 경우",
                examples=[
                    OpenApiExample(
                        "QuestionGenerationFailed",
                        value={
                            "detail": "설문 첫 질문을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
                        },
                    )
                ],
            ),
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = SurveyChatbotSessionService()
        result = service.create_session(
            user=request.user,
            is_reset=serializer.validated_data["is_reset"],
        )

        response_serializer = SurveyChatbotSessionCreateResponseSerializer(
            result.as_dict()
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class SurveyChatbotSessionResetAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["survey"],
        summary="설문 챗봇 세션 초기화",
        description="현재 유저의 설문 챗봇 세션을 초기화하고 새 첫 질문을 제공합니다.",
        request=None,
        responses={
            201: SurveyChatbotSessionResetResponseSerializer,
            401: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="인증 정보가 없거나 유효하지 않은 경우",
                examples=[
                    OpenApiExample(
                        "Unauthorized",
                        value={
                            "detail": "자격 인증데이터(authentication credentials)가 제공되지 않았습니다."
                        },
                    )
                ],
            ),
            503: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="LLM 첫 질문 생성에 실패한 경우",
                examples=[
                    OpenApiExample(
                        "QuestionGenerationFailed",
                        value={
                            "detail": "설문 첫 질문을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
                        },
                    )
                ],
            ),
        },
    )
    def post(self, request):
        service = SurveyChatbotSessionService()
        result = service.create_session(
            user=request.user,
            is_reset=True,
        )

        response_serializer = SurveyChatbotSessionResetResponseSerializer(
            result.as_dict()
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
