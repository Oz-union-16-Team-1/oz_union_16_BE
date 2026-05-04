from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.chatbot.serializers.chatbot_sessions_serializers import (
    ChatbotSessionStatusResponseSerializer,
)
from apps.chatbot.services.chatbot_sessions_services import (
    build_session_payload,
    get_chatbot_session,
)


class ChatbotSessionStatusAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def get(self, request, session_id, *args, **kwargs):
        try:
            session = get_chatbot_session(session_id)
            if session is None:
                return JsonResponse(
                    {"error_detail": "유효하지 않은 session_id 입니다."},
                    status=404,
                    json_dumps_params={"ensure_ascii": False},
                )

            response_serializer = ChatbotSessionStatusResponseSerializer(
                {
                    **build_session_payload(session),
                    "is_expired": session.is_expired,
                }
            )
            return JsonResponse(
                response_serializer.data,
                status=200,
                json_dumps_params={"ensure_ascii": False},
            )

        except Exception:
            return JsonResponse(
                {"error_detail": "세션 상태 조회 중 서버 오류가 발생했습니다."},
                status=500,
                json_dumps_params={"ensure_ascii": False},
            )
