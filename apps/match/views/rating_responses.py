from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.match.serializers.rating_responses import (
    MatchResponsesRequestSerializer,
    MatchResponsesResponseSerializer,
)
from apps.match.services.responses_submit import (
    MatchResponsesGameNotFoundError,
    MatchResponsesSubmitService,
    MatchResponsesValidationError,
)


class MatchResponsesAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MatchResponsesRequestSerializer
    service_class = MatchResponsesSubmitService

    @extend_schema(
        operation_id="v1_match_responses",
        tags=["match"],
        summary="매칭 레이팅 제출 API",
        description=(
            "사용자가 candidates에서 받은 게임에 대한 별점(1~5) 및 좋아요 상태를 제출합니다. "
            "요청의 genre_id/retry_no(및 candidate_date) 기준 후보 세트에 포함되지 않은 game_id가 있으면 실패합니다. "
            "is_liked 미전달 시 기존 좋아요 상태를 유지합니다."
        ),
        request=MatchResponsesRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=MatchResponsesResponseSerializer,
                description="요청이 성공적으로 처리되었고, 평가 결과가 누적 반영되었습니다.",
            ),
            400: OpenApiResponse(
                description="요청 바디가 유효하지 않거나 후보 세트에 없는 game_id가 포함된 경우 발생합니다.",
            ),
            401: OpenApiResponse(
                description="인증 토큰이 없거나 유효하지 않아 요청을 인증할 수 없습니다.",
            ),
            404: OpenApiResponse(
                description="요청한 game_id 중 존재하지 않거나 사용 불가(is_ban) 게임이 포함된 경우 발생합니다.",
            ),
        },
    )
    def post(self, request):
        req_serializer = self.get_serializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        data = req_serializer.validated_data

        try:
            result = self.service_class().submit(
                user_id=request.user.id,
                genre_id=data["genre_id"],
                retry_no=data["retry_no"],
                candidate_date=data.get("candidate_date"),
                match_result=data["match_result"],
            )
        except MatchResponsesValidationError as exc:
            raise ValidationError(str(exc)) from exc
        except MatchResponsesGameNotFoundError as exc:
            raise NotFound(str(exc)) from exc

        res_serializer = MatchResponsesResponseSerializer(result)
        return Response(res_serializer.data, status=status.HTTP_200_OK)
