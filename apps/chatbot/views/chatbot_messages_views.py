from django.http import JsonResponse
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.chatbot.serializers.chatbot_errors_serializers import (
    ChatbotErrorResponseSerializer,
)
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


class ChatbotMessageAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    @extend_schema(
        summary="AI 챗봇 메시지 전송 API",
        description=(
            "AI 챗봇 질문을 등록하고 세션 정보를 반환합니다. "
            "이 API 호출 후 응답의 `session_id` 를 가지고 "
            "GET `/api/v1/chatbot/stream?session_id=...` 를 호출해야 답변이 SSE 로 스트리밍됩니다.\n\n"
            "- **최초 요청**: `session_id` 를 생략하면 서버가 새 세션을 발급합니다.\n"
            "- **후속 요청**: 응답으로 받은 `session_id` 를 함께 보내면 같은 세션을 이어 사용합니다.\n"
            "- 인증 필요 여부: 불필요 (Authorization 헤더 사용 안 함, 비회원 사용 가능)\n"
            "- 세션은 생성 또는 마지막 유효 요청 시점 기준 30분 동안 유지되며, 만료 시 새로 시작해야 합니다."
        ),
        request=ChatbotMessageRequestSerializer,
        responses={
            200: ChatbotMessageResponseSerializer,
            400: OpenApiResponse(
                response=ChatbotErrorResponseSerializer,
                description="Bad Request",
                examples=[
                    OpenApiExample(
                        "메시지 검증 실패",
                        value={
                            "error_detail": "메시지는 공백일 수 없고 2자 이상이어야 합니다."
                        },
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
                            "error_detail": "만료되었거나 유효하지 않은 session_id 입니다."
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
                        value={"error_detail": "요청 처리 중 오류가 발생했습니다."},
                    )
                ],
            ),
        },
        examples=[
            OpenApiExample(
                "최초 요청 (세션 신규 발급)",
                summary="처음 보낼 때는 session_id 를 생략합니다.",
                value={"message": "아이디는 어디서 찾나요?"},
                request_only=True,
            ),
            OpenApiExample(
                "후속 요청 (기존 세션 유지)",
                summary="응답으로 받은 session_id 를 그대로 넣어 같은 세션을 이어갑니다.",
                value={
                    "message": "그럼 비밀번호는 어떻게 바꿔요?",
                    "session_id": "1ae7032f-1051-441c-ae9d-07b7eb6d2b7d",
                },
                request_only=True,
            ),
            OpenApiExample(
                "응답 예시",
                value={
                    "session_id": "1ae7032f-1051-441c-ae9d-07b7eb6d2b7d",
                    "expires_at": "2026-05-04T07:40:35.712256+00:00",
                },
                response_only=True,
            ),
        ],
        tags=["chatbot"],
        auth=[],
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
