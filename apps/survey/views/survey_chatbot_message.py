from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.survey.serializers.survey_chatbot_message import (
    SurveyChatbotMessageErrorResponseSerializer,
    SurveyChatbotMessageLockedResponseSerializer,
    SurveyChatbotMessageRequestSerializer,
    SurveyChatbotMessageResponseSerializer,
)
from apps.survey.services.survey_chatbot_message import (
    SurveyChatbotMessageService,
    SurveyChatbotSessionLocked,
)


class SurveyChatbotMessageAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SurveyChatbotMessageRequestSerializer

    @extend_schema(
        tags=["survey"],
        summary="설문 챗봇 대화 진행 및 요약",
        description=(
            "설문 세션에 사용자 답변을 저장하고 다음 질문을 생성합니다. "
            "목표 질문 수에 도달하면 설문 요약을 저장하고 추천 준비 상태를 반환합니다."
        ),
        request=SurveyChatbotMessageRequestSerializer,
        responses={
            200: SurveyChatbotMessageResponseSerializer,
            401: OpenApiResponse(
                response=SurveyChatbotMessageErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "Unauthorized",
                        value={
                            "error_detail": "인증 정보가 유효하지 않거나 만료되었습니다."
                        },
                    )
                ],
            ),
            409: OpenApiResponse(
                response=SurveyChatbotMessageErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "SessionClosed",
                        value={"error_detail": "이미 종료된 설문 세션입니다."},
                    )
                ],
            ),
            423: OpenApiResponse(
                response=SurveyChatbotMessageLockedResponseSerializer,
                examples=[
                    OpenApiExample(
                        "SessionLocked",
                        value={
                            "error_detail": "질문과 무관한 답변이 반복되어 5분간 설문이 비활성화되었습니다.",
                            "retry_after_seconds": 300,
                        },
                    )
                ],
            ),
            503: OpenApiResponse(
                response=SurveyChatbotMessageErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "QuestionGenerationFailed",
                        value={
                            "error_detail": "설문 첫 질문을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
                        },
                    ),
                    OpenApiExample(
                        "SummaryGenerationFailed",
                        value={
                            "error_detail": "설문 결과를 정리하지 못했습니다. 잠시 후 다시 시도해주세요."
                        },
                    ),
                ],
            ),
        },
    )
    def post(self, request, session_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = SurveyChatbotMessageService()
        try:
            result = service.handle_message(
                user=request.user,
                session_id=session_id,
                message=serializer.validated_data["message"],
            )
        except SurveyChatbotSessionLocked as exc:
            return Response(
                {
                    "error_detail": str(exc.detail),
                    "retry_after_seconds": exc.retry_after_seconds,
                },
                status=status.HTTP_423_LOCKED,
            )

        response_serializer = SurveyChatbotMessageResponseSerializer(result.as_dict())
        return Response(response_serializer.data, status=status.HTTP_200_OK)
