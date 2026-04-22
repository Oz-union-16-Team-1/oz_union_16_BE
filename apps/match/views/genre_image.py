from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.match.serializers.genre_image import (
    MatchGenreImageQuerySerializer,
    MatchGenreImageResponseSerializer,
)
from apps.match.services.genre_image_query import MatchGenreImageQueryService


class MatchGenreImageAPIView(APIView):
    permission_classes = [IsAuthenticated]
    service_class = MatchGenreImageQueryService

    @extend_schema(
        operation_id="v1_match_genres_image_url",
        tags=["match"],
        summary="매칭 장르별 이미지 전달 API",
        description=(
            "🖼️ 장르 선택 화면에 사용할 대표 이미지를 반환합니다. "
            "대표 이미지는 장르별 인기 게임을 기준으로 주기적으로 최신화되므로, "
            "응답 이미지가 변경될 수 있습니다. "
            "⚠️ genre_id는 1~8 범위의 정수만 허용됩니다. "
            "장르 매핑: "
            "(1) 액션/격투, (2) 어드벤처/플랫폼, (3) RPG/스토리, (4) 전략/시뮬, "
            "(5) 스포츠/레이싱, (6) 두뇌/전략, (7) 슈팅, (8) 음악/리듬"
        ),
        parameters=[MatchGenreImageQuerySerializer],
        responses={
            200: MatchGenreImageResponseSerializer,
            400: OpenApiResponse(
                description="error_detail: 유효하지 않은 genre_id 입니다."
            ),
            401: OpenApiResponse(
                description="error_detail: 자격 인증 데이터가 제공되지 않았습니다."
            ),
            404: OpenApiResponse(
                description="error_detail: 해당 장르의 이미지를 찾을 수 없습니다."
            ),
            503: OpenApiResponse(
                description="error_detail: 이미지 캐시 서비스가 일시적으로 불가합니다."
            ),
        },
    )
    def get(self, request):
        query_serializer = MatchGenreImageQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        genre_id = query_serializer.validated_data["genre_id"]
        data = self.service_class().get_genre_image(genre_id)

        response_serializer = MatchGenreImageResponseSerializer(data)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
