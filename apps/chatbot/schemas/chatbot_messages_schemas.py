from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema

from apps.chatbot.serializers.chatbot_errors_serializers import (
    ChatbotErrorResponseSerializer,
)
from apps.chatbot.serializers.chatbot_messages_serializers import (
    ChatbotMessageRequestSerializer,
    ChatbotMessageSchemaResponseSerializer,
)

chatbot_message_schema = extend_schema(
    summary="AI 챗봇 메시지 전송 API",
    description=(
        "AI 챗봇 메시지를 전송합니다.\n\n"
        "- 인증 필요 여부: 불필요\n"
        "- 비회원 사용: 가능\n"
        "- Authorization 헤더: 사용하지 않음\n"
        "- 세션은 생성 또는 마지막 유효 요청 시점 기준 30분 동안 유지"
    ),
    request=ChatbotMessageRequestSerializer,
    responses={
        200: ChatbotMessageSchemaResponseSerializer,
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
            "요청 예시",
            value={
                "message": "아이디는 어디서 찾나요?",
                "session_id": "1ae7032f-1051-441c-ae9d-07b7eb6d2b7d",
            },
            request_only=True,
        ),
        OpenApiExample(
            "응답 예시",
            value={"session_id": "1ae7032f-1051-441c-ae9d-07b7eb6d2b7d"},
            response_only=True,
        ),
    ],
    tags=["chatbot"],
    auth=[],
)
