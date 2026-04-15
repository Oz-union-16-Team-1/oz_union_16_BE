from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.chatbot.serializers.chatbot_serializers import ChatbotMessageRequestSerializer
from apps.chatbot.services.chatbot_services import (
    create_chatbot_session,
    get_valid_chatbot_session,
    save_question_to_cache,
)


class ChatbotMessageView(APIView):
    def post(self, request):
        serializer = ChatbotMessageRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {"detail": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = serializer.validated_data["message"]
        session_id = serializer.validated_data.get("session_id")

        # 세션 처리
        if session_id:
            session = get_valid_chatbot_session(session_id)
            if not session:
                return Response(
                    {"detail": "만료되었거나 유효하지 않은 session_id 입니다."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            session = create_chatbot_session()

        # 질문 캐시에 저장
        save_question_to_cache(session.chatbot_sessions_id, message)

        return Response(
            {"session_id": session.chatbot_sessions_id},
            status=status.HTTP_200_OK,
        )