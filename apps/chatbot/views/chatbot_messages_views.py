from django.http import JsonResponse
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.chatbot.schemas.chatbot_messages_schemas import chatbot_message_schema
from apps.chatbot.serializers.chatbot_messages_serializers import (
    ChatbotMessageRequestSerializer,
    ChatbotMessageResponseSerializer,
)
from apps.chatbot.services.chatbot_messages_services import save_question_to_cache
from apps.chatbot.services.chatbot_sessions_services import (
    build_session_payload,
    create_chatbot_session,
    get_valid_chatbot_session,
)
from apps.chatbot.services.chatbot_streaming_services import is_streaming


class ChatbotMessageAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    @chatbot_message_schema
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
                build_session_payload(session)
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
