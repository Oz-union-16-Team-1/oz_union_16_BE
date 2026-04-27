from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.match.serializers.candidates import (
    MatchCandidatesQuerySerializer,
    MatchCandidatesResponseSerializer,
)
from apps.match.services.candidates_query import MatchCandidatesQueryService


class MatchCandidatesAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MatchCandidatesQuerySerializer
    service_class = MatchCandidatesQueryService

    @extend_schema(
        operation_id="v1_match_candidates",
        tags=["match"],
        summary="매칭 평가 대상 게임 목록 조회 API",
        description=(
            "선택한 장르 기준으로 평가 대상 게임 목록을 반환합니다. "
            "같은 날 기준으로, 같은 장르 재시도 시, retry_no이 증가합니다. "
            "다른 retry_no를 통해 같은 날에도 다른 후보 집합을 받을 수 있습니다."
        ),
        parameters=[MatchCandidatesQuerySerializer],
        responses={
            200: OpenApiResponse(
                response=MatchCandidatesResponseSerializer,
                description="요청이 성공적으로 처리되었으며, 선택한 장르의 평가 대상 게임 목록을 반환합니다. retry_no 값에 따라 같은 날에도 다른 후보 집합이 반환될 수 있습니다.",
            ),
            400: OpenApiResponse(
                description="요청 파라미터가 유효하지 않을 때 발생합니다. (예: genre_id가 1~8 범위를 벗어남, retry_no가 0 미만)",
            ),
            401: OpenApiResponse(
                description="인증 토큰이 없거나 유효하지 않아 요청을 인증할 수 없습니다.",
            ),
            404: OpenApiResponse(
                description="요청은 정상이나, 조건(장르/제외 규칙/필터)을 만족하는 후보 게임이 없어 결과를 반환할 수 없습니다.",
            ),
            503: OpenApiResponse(
                description="후보 조회에 필요한 내부/외부 게임 데이터 처리 중 일시적 장애가 발생했습니다. 잠시 후 다시 시도해야 합니다.",
            ),
        },
    )
    def get(self, request):
        query_serializer = self.get_serializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        genre_id = query_serializer.validated_data["genre_id"]
        retry_no = query_serializer.validated_data["retry_no"]

        data = self.service_class().get_candidates(
            user_id=request.user.id,
            genre_id=genre_id,
            retry_no=retry_no,
        )

        if data["count"] == 0:
            raise NotFound("해당 장르의 게임을 찾을 수 없습니다.")

        response_serializer = MatchCandidatesResponseSerializer(data)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
