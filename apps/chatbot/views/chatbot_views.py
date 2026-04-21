from django.http import JsonResponse, StreamingHttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.chatbot.serializers.chatbot_serializers import (
    ChatbotMessageRequestSerializer,
    ChatbotMessageResponseSerializer,
    ChatbotStreamQuerySerializer,
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

    def post(self, request, *args, **kwargs):
        serializer = ChatbotMessageRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return JsonResponse(
                {
                    "detail": serializer.errors.get(
                        "message",
                        ["요청 값이 올바르지 않습니다."],
                    )[0]
                },
                status=400,
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
                        {"detail": "만료되었거나 유효하지 않은 session_id 입니다."},
                        status=404,
                    )

                if is_streaming(session.pk):
                    return JsonResponse(
                        {"detail": "이미 스트리밍이 진행 중입니다."},
                        status=409,
                    )

            save_question_to_cache(session.pk, message)

            response_serializer = ChatbotMessageResponseSerializer(
                {"session_id": session.pk}
            )
            return JsonResponse(response_serializer.data, status=200)

        except Exception as e:
            return JsonResponse(
                {"detail": str(e)},
                status=500,
            )


class ChatbotStreamAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        serializer = ChatbotStreamQuerySerializer(data=request.query_params)

        if not serializer.is_valid():
            return JsonResponse(
                {"detail": "잘못된 session_id 입니다."},
                status=400,
            )

        session_id = serializer.validated_data["session_id"]

        try:
            session = get_valid_chatbot_session(session_id)
            if session is None:
                return JsonResponse(
                    {"detail": "스트리밍 대상 세션을 찾을 수 없습니다."},
                    status=404,
                )

            question = get_question_from_cache(session_id)
            if not question:
                return JsonResponse(
                    {"detail": "스트리밍 대상 질문이 없습니다."},
                    status=404,
                )

            if not acquire_stream_lock(session_id):
                return JsonResponse(
                    {"detail": "이미 스트리밍이 진행 중입니다."},
                    status=409,
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

        except Exception as e:
            release_stream_lock(session_id)
            return JsonResponse(
                {"detail": str(e)},
                status=500,
            )