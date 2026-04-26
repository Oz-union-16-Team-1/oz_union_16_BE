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
            200: MatchCandidatesResponseSerializer,
            400: OpenApiResponse(description="error_detail: 유효하지 않은 genre_id 입니다."),
            401: OpenApiResponse(description="error_detail: 자격 인증 데이터가 제공되지 않았습니다."),
            404: OpenApiResponse(description="error_detail: 해당 장르의 게임을 찾을 수 없습니다."),
            503: OpenApiResponse(
                description="error_detail: 외부 게임 데이터 서비스가 일시적으로 불가합니다."
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
