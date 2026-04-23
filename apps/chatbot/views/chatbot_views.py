from django.http import JsonResponse, StreamingHttpResponse
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.chatbot.serializers.chatbot_serializers import (
    ChatbotMessageRequestSerializer,
    ChatbotMessageResponseSerializer,
)
from apps.chatbot.services.chatbot_services import (
    acquire_stream_lock,
    create_chatbot_session,
    delete_question_from_cache,
    generate_stream,
    get_question_from_cache,
    get_valid_chatbot_session,
    is_streaming,
    release_stream_lock,
    save_question_to_cache,
)


class ChatbotMessageAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="chatbot message",
        description="챗봇 메시지를 전송하고 session_id를 반환합니다.",
        request=ChatbotMessageRequestSerializer,
        responses={
            200: ChatbotMessageResponseSerializer,
            400: OpenApiResponse(description="잘못된 요청입니다."),
            404: OpenApiResponse(
                description="만료되었거나 유효하지 않은 session_id 입니다."
            ),
            409: OpenApiResponse(description="이미 스트리밍이 진행 중입니다."),
            500: OpenApiResponse(
                description="메시지 요청 처리 중 서버 오류가 발생했습니다."
            ),
        },
        examples=[
            OpenApiExample(
                "신규 세션 메시지 예시",
                value={"message": "환불은 어떻게 해요?"},
                request_only=True,
            ),
            OpenApiExample(
                "기존 세션 메시지 예시",
                value={
                    "message": "환불은 어떻게 해요?",
                    "session_id": "1ae7032f-1051-441c-ae9d-07b7eb6d2b7d",
                },
                request_only=True,
            ),
        ],
        tags=["chatbot"],
    )
    def post(self, request, *args, **kwargs):
        serializer = ChatbotMessageRequestSerializer(data=request.data)

        if not serializer.is_valid():
            first_error = next(iter(serializer.errors.values()))[0]
            return JsonResponse(
                {"error_detail": first_error},
                status=400,
                json_dumps_params={"ensure_ascii": False},
            )

        message = serializer.validated_data["message"]
        session_id = serializer.validated_data.get("session_id")

        try:
            if session_id is None:
                session = create_chatbot_session()
            else:
                session = get_valid_chatbot_session(session_id)
                if session is None:
                    return JsonResponse(
                        {
                            "error_detail": "만료되었거나 유효하지 않은 session_id 입니다."
                        },
                        status=404,
                        json_dumps_params={"ensure_ascii": False},
                    )

                if is_streaming(session.pk):
                    return JsonResponse(
                        {"error_detail": "이미 스트리밍이 진행 중입니다."},
                        status=409,
                        json_dumps_params={"ensure_ascii": False},
                    )

            save_question_to_cache(session.pk, message)

            response_serializer = ChatbotMessageResponseSerializer(
                {"session_id": session.pk}
            )
            return JsonResponse(
                response_serializer.data,
                status=200,
                json_dumps_params={"ensure_ascii": False},
            )

        except Exception:
            return JsonResponse(
                {"error_detail": "메시지 요청 처리 중 서버 오류가 발생했습니다."},
                status=500,
                json_dumps_params={"ensure_ascii": False},
            )


class ChatbotStreamAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary="chatbot stream",
        description="session_id로 챗봇 응답을 SSE 스트리밍으로 반환합니다.",
        parameters=[
            OpenApiParameter(
                name="session_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="챗봇 세션 UUID",
            ),
        ],
        responses={
            200: OpenApiResponse(description="text/event-stream"),
            400: OpenApiResponse(description="잘못된 요청입니다."),
            404: OpenApiResponse(
                description="만료되었거나 유효하지 않은 session_id 입니다."
            ),
            409: OpenApiResponse(description="이미 스트리밍이 진행 중입니다."),
            500: OpenApiResponse(
                description="메시지 요청 처리 중 서버 오류가 발생했습니다."
            ),
        },
        tags=["chatbot"],
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
                    yield from generate_stream(session_id=session_id, question=question)
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
