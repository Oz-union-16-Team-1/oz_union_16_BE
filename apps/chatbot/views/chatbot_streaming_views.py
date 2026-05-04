from uuid import UUID

from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from apps.chatbot.schemas.chatbot_streaming_schemas import chatbot_streaming_schema
from apps.chatbot.services.chatbot_messages_services import (
    delete_question_from_cache,
    get_question_from_cache,
)
from apps.chatbot.services.chatbot_sessions_services import get_valid_chatbot_session
from apps.chatbot.services.chatbot_streaming_services import (
    acquire_stream_lock,
    generate_stream,
    release_stream_lock,
)
from apps.chatbot.views.renderers import EventStreamRenderer


class ChatbotStreamAPIView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [EventStreamRenderer, JSONRenderer]

    @chatbot_streaming_schema
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
            session = get_valid_chatbot_session(session_id)
            if session is None:
                return JsonResponse(
                    {"error_detail": "스트리밍 대상 세션을 찾을 수 없습니다."},
                    status=404,
                    json_dumps_params={"ensure_ascii": False},
                )

            question = get_question_from_cache(session_id)
            if not question:
                return JsonResponse(
                    {"error_detail": "스트리밍 대상 질문이 없습니다."},
                    status=404,
                    json_dumps_params={"ensure_ascii": False},
                )

            if not acquire_stream_lock(session_id):
                return JsonResponse(
                    {"error_detail": "이미 스트리밍이 진행 중입니다."},
                    status=409,
                    json_dumps_params={"ensure_ascii": False},
                )

            def stream_response():
                try:
                    yield from generate_stream(session=session, question=question)
                finally:
                    delete_question_from_cache(session_id)
                    release_stream_lock(session_id)

            response = StreamingHttpResponse(
                streaming_content=stream_response(),
                content_type="text/event-stream",
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        except Exception:
            release_stream_lock(session_id)
            return JsonResponse(
                {"error_detail": "스트리밍 처리 중 서버 오류가 발생했습니다."},
                status=500,
                json_dumps_params={"ensure_ascii": False},
            )
