from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.survey.serializers.survey_chatbot_session import SurveyErrorResponseSerializer
from apps.survey.serializers.survey_recommendation import (
    SurveyRecommendationQuerySerializer,
    SurveyRecommendationResponseSerializer,
)
from apps.survey.services.survey_recommendation import SurveyRecommendationService


class SurveyRecommendationAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SurveyRecommendationQuerySerializer

    @extend_schema(
        tags=["survey"],
        summary="설문 결과 게임 추천 조회",
        description="종료된 설문 세션 기준으로 게임 추천 목록을 커서 페이지네이션으로 조회합니다.",
        parameters=[
            OpenApiParameter(
                name="cursor",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="이전 응답의 next 값, 없으면 첫 페이지",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="페이지 크기, 기본 5 최대 15",
            ),
        ],
        responses={
            200: SurveyRecommendationResponseSerializer,
            401: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "Unauthorized",
                        value={
                            "detail": "자격 인증데이터(authentication credentials)가 제공되지 않았습니다."
                        },
                    )
                ],
            ),
            409: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "RecommendationNotReady",
                        value={"detail": "설문 추천 준비가 아직 완료되지 않았습니다."},
                    )
                ],
            ),
            503: OpenApiResponse(
                response=SurveyErrorResponseSerializer,
                examples=[
                    OpenApiExample(
                        "RecommendationUnavailable",
                        value={
                            "detail": "설문 추천 결과를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."
                        },
                    )
                ],
            ),
        },
    )
    def get(self, request, session_id):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        service = SurveyRecommendationService()
        result = service.get_recommendations(
            user=request.user,
            session_id=str(session_id),
            cursor=serializer.validated_data.get("cursor"),
            page_size=serializer.validated_data["page_size"],
        )
        response_serializer = SurveyRecommendationResponseSerializer(result)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
