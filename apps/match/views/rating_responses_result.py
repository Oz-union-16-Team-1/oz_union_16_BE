from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.match.serializers.rating_responses_result import (
    MatchResponsesResultQuerySerializer,
    MatchResponsesResultResponseSerializer,
)
from apps.match.services.responses_result_query import (
    MatchResponsesResultDataUnavailable,
    MatchResponsesResultQueryService,
    MatchResponsesResultValidationError,
)


class MatchResponsesResultServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "추천 데이터 조회 중 외부 서비스 오류가 발생했습니다."


class MatchResponsesResultAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MatchResponsesResultQuerySerializer
    service_class = MatchResponsesResultQueryService

    @extend_schema(
        operation_id="v1_match_responses_result",
        tags=["match"],
        summary="매칭 결과 게임 목록 조회 API",
        description=(
            "사용자 매칭 결과 게임 목록을 조회합니다. "
            "정렬은 final_score DESC, game_id DESC로 고정됩니다. "
            "rating 필드는 게임 평점(0~100)을 의미합니다."
        ),
        parameters=[MatchResponsesResultQuerySerializer],
        responses={
            200: OpenApiResponse(
                response=MatchResponsesResultResponseSerializer,
                description="요청이 성공적으로 처리되었으며, final_score 기준 정렬된 추천 결과를 반환합니다.",
            ),
            400: OpenApiResponse(
                description="요청 파라미터가 유효하지 않을 때 발생합니다. (예: genre_id 범위 오류, cursor 형식 오류, page_size 범위 오류)",
            ),
            401: OpenApiResponse(
                description="인증 토큰이 없거나 유효하지 않아 요청을 인증할 수 없습니다.",
            ),
            404: OpenApiResponse(
                description="요청은 정상이지만 조건을 만족하는 매칭 추천 결과를 찾을 수 없습니다.",
            ),
            503: OpenApiResponse(
                description="추천 데이터 조회/계산 과정에서 외부 의존성 장애가 발생해 일시적으로 처리할 수 없습니다.",
            ),
        },
    )
    def get(self, request):
        query_serializer = self.get_serializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        data = query_serializer.validated_data

        try:
            result = self.service_class().get_results(
                user_id=request.user.id,
                genre_id=data["genre_id"],
                cursor=data.get("cursor"),
                page_size=data.get("page_size", 5),
            )
        except MatchResponsesResultValidationError as exc:
            raise ValidationError(str(exc)) from exc
        except MatchResponsesResultDataUnavailable as exc:
            raise MatchResponsesResultServiceUnavailable() from exc

        if result["count"] == 0:
            raise NotFound("매칭 추천 결과를 찾을 수 없습니다.")

        response_serializer = MatchResponsesResultResponseSerializer(result)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
