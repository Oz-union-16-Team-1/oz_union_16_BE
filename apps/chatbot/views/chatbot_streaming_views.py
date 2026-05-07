from uuid import UUID

from django.http import JsonResponse, StreamingHttpResponse
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from apps.chatbot.serializers.chatbot_errors_serializers import (
    ChatbotErrorResponseSerializer,
)
from apps.chatbot.services.chatbot_sessions_services import claim_pending_question
from apps.chatbot.services.chatbot_streaming_services import generate_stream
from apps.chatbot.views.renderers import EventStreamRenderer


class ChatbotStreamAPIView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [EventStreamRenderer, JSONRenderer]

    @extend_schema(
        summary="AI 챗봇 응답 스트리밍 API",
        description=(
            "POST `/api/v1/chatbot/messages` 에서 받은 `session_id` 로 답변을 SSE 스트리밍으로 반환합니다.\n\n"
            "- 호출 순서: 먼저 POST `/api/v1/chatbot/messages` 로 질문을 등록하고, "
            "응답의 `session_id` 를 이 API 의 쿼리 파라미터에 넣어 호출하세요.\n"
            "- **1회용**: 한 번 호출하면 등록된 질문이 소비됩니다. "
            "추가 답변을 받으려면 POST `/api/v1/chatbot/messages` 부터 다시 호출해야 합니다.\n"
            "- 응답 이벤트: `start` → `chunk` × N → `complete` 순서로 송출됩니다.\n"
            "- 인증 필요 여부: 불필요 (Authorization 헤더 사용 안 함, 비회원 사용 가능)\n"
            "- 세션은 마지막 유효 요청 시점 기준 30분 동안 유지되며, 만료 시 새로 시작해야 합니다."
        ),
        parameters=[
            OpenApiParameter(
                name="session_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description=(
                    "AI 챗봇 메시지 전송 API를 통해 생성된 현재 화면 한정 임시 대화 식별자입니다. "
                    "대화는 현재 화면에서만 일시적으로 유지되며, 페이지 이동, 새로고침, 챗봇 종료 "
                    "또는 UI의 '대화 초기화' 버튼 클릭 시 기존 session_id는 폐기됩니다."
                ),
            ),
        ],
        responses={
            200: OpenApiResponse(
                description=(
                    "text/event-stream (SSE 스트리밍)\n\n"
                    "event: start\n"
                    'data: {"session_id": "b89a093b-0bae-4e8c-b6f2-2871a60c5dc4", '
                    '"expires_at": "2026-05-04T08:25:53.330521+00:00", '
                    '"expires_in_seconds": 1800, "session_ttl_seconds": 1800}\n\n\n'
                    'event: chunk\ndata: {"content":"아이디는"}\n\n'
                    'event: chunk\ndata: {"content":" 본인 인증을 통해"}\n\n'
                    'event: chunk\ndata: {"content":" 찾을 수 있습니다."}\n\n'
                    "event: complete\n"
                    'data: {"session_id": "b89a093b-0bae-4e8c-b6f2-2871a60c5dc4", '
                    '"expires_at": "2026-05-04T08:25:53.330521+00:00", '
                    '"expires_in_seconds": 1800, "session_ttl_seconds": 1800}'
                )
            ),
            400: OpenApiResponse(
                response=ChatbotErrorResponseSerializer,
                description="Bad Request",
                examples=[
                    OpenApiExample(
                        "잘못된 session_id",
                        value={"error_detail": "잘못된 session_id 입니다."},
                    )
                ],
            ),
            404: OpenApiResponse(
                response=ChatbotErrorResponseSerializer,
                description="Not Found",
                examples=[
                    OpenApiExample(
                        "세션 없음",
                        value={
                            "error_detail": "스트리밍 대상 세션을 찾을 수 없습니다."
                        },
                    )
                ],
            ),
            500: OpenApiResponse(
                response=ChatbotErrorResponseSerializer,
                description="Internal Server Error",
                examples=[
                    OpenApiExample(
                        "서버 오류",
                        value={"error_detail": "스트리밍 중 오류가 발생했습니다."},
                    )
                ],
            ),
        },
        tags=["chatbot"],
        auth=[],
    )
    def get(self, request, *args, **kwargs):
        session_id = request.query_params.get("session_id")

        if not session_id:
            return JsonResponse(
                {"error_detail": "session_id는 필수 입력값입니다."},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        try:
            UUID(str(session_id))
        except ValueError:
            return JsonResponse(
                {"error_detail": "잘못된 session_id 입니다."},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        try:
            session, question = claim_pending_question(session_id)
            if session is None:
                return JsonResponse(
                    {"error_detail": "스트리밍 대상 세션을 찾을 수 없습니다."},
                    status=404,
                    json_dumps_params={"ensure_ascii": False},
                )
            if question is None:
                return JsonResponse(
                    {"error_detail": "스트리밍 대상 질문이 없습니다."},
                    status=404,
                    json_dumps_params={"ensure_ascii": False},
                )

            response = StreamingHttpResponse(
                streaming_content=generate_stream(session=session, question=question),
                content_type="text/event-stream",
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        except Exception:
            return JsonResponse(
                {"error_detail": "스트리밍 처리 중 서버 오류가 발생했습니다."},
                status=500,
                json_dumps_params={"ensure_ascii": False},
            )
