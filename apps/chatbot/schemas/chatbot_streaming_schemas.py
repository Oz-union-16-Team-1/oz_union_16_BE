from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)

from apps.chatbot.serializers.chatbot_errors_serializers import (
    ChatbotErrorResponseSerializer,
)

chatbot_streaming_schema = extend_schema(
    summary="AI 챗봇 응답 스트리밍 API",
    description=(
        "session_id로 챗봇 응답을 SSE 스트리밍으로 반환합니다.\n\n"
        "- 인증 필요 여부: 불필요\n"
        "- 비회원 사용: 가능\n"
        "- Authorization 헤더: 사용하지 않음\n"
        "- 요청 시점 기준 30분 동안 유지되며, 30분이 지나면 만료 처리"
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
                    value={"error_detail": "스트리밍 대상 세션을 찾을 수 없습니다."},
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
