from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.survey.serializers.survey_chatbot_session import (
    SurveyChatbotSessionCreateResponseSerializer,
    SurveyChatbotSessionResetResponseSerializer,
    SurveyErrorResponseSerializer,
)
from apps.survey.services.survey_chatbot_session import SurveyChatbotSessionService


class SurveyChatbotSessionCreateAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SurveyChatbotSessionCreateResponseSerializer

    @extend_schema(
        tags=["survey"],
        summary="설문 챗봇 세션 시작",
        description="유저별 설문 챗봇 세션을 생성하거나 기존 세션을 반환하고 첫 질문을 제공합니다.",
        request=None,
        responses={
            201: SurveyChatbotSessionCreateResponseSerializer,
            401: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="인증 정보가 없거나 유효하지 않은 경우",
                examples=[
                    OpenApiExample(
                        "Unauthorized",
                        value={
                            "error_detail": "설문 세션이 만료되었습니다. 다시 시작해주세요."
                        },
                    )
                ],
            ),
            403: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="해당 세션에 대한 접근 권한이 없는 경우",
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={
                            "error_detail": "해당 세션에 대한 접근 권한이 없습니다."
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
                            "error_detail": "응답을 생성하는 도중 오류가 발생하였습니다."
                        },
                    )
                ],
            ),
        },
    )
    def post(self, request):
        service = SurveyChatbotSessionService()
        result = service.create_session(user=request.user)

        response_serializer = SurveyChatbotSessionCreateResponseSerializer(
            result.as_dict()
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class SurveyChatbotSessionResetAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SurveyChatbotSessionResetResponseSerializer

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
                            "error_detail": "자격 인증 데이터가 제공되지 않았습니다."
                        },
                    )
                ],
            ),
            403: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="해당 세션에 대한 접근 권한이 없는 경우",
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={
                            "error_detail": "해당 세션에 대한 접근 권한이 없습니다."
                        },
                    )
                ],
            ),
            404: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="초기화할 세션을 찾을 수 없는 경우",
                examples=[
                    OpenApiExample(
                        "NotFound",
                        value={"error_detail": "해당 세션을 찾을 수 없습니다."},
                    )
                ],
            ),
            503: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                description="LLM 첫 질문 생성에 실패한 경우",
                examples=[
                    OpenApiExample(
                        "QuestionGenerationFailed",
                        value={"error_detail": "현재 서비스를 이용할 수 없습니다."},
                    )
                ],
            ),
        },
    )
    def post(self, request):
        service = SurveyChatbotSessionService()
        result = service.reset_session(user=request.user)

        response_serializer = SurveyChatbotSessionResetResponseSerializer(
            result.as_dict()
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
