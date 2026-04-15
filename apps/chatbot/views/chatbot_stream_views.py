from django.http import StreamingHttpResponse
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response

from apps.chatbot.services.chatbot_services import (
    get_valid_chatbot_session,
    get_question_from_cache,
    delete_question_from_cache,
    generate_stream,
)


class ChatbotStreamView(APIView):
    def get(self, request):
        session_id = request.GET.get("session_id")

        if not session_id:
            return Response(
                {"detail": "잘못된 session_id 입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = get_valid_chatbot_session(int(session_id))
        if not session:
            return Response(
                {"detail": "스트리밍 대상 세션을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        question = get_question_from_cache(session.chatbot_sessions_id)
        if not question:
            return Response(
                {"detail": "질문이 존재하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = StreamingHttpResponse(
            generate_stream(session.chatbot_sessions_id, question),
            content_type="text/event-stream",
        )

        delete_question_from_cache(session.chatbot_sessions_id)

        return response