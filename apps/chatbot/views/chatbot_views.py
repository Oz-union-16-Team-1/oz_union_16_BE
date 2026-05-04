from django.http import JsonResponse, StreamingHttpResponse
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.views import APIView

from apps.chatbot.serializers.chatbot_serializers import (
    ChatbotErrorResponseSerializer,
    ChatbotMessageRequestSerializer,
    ChatbotMessageResponseSerializer,
    ChatbotMessageSchemaResponseSerializer,
    ChatbotSessionStatusResponseSerializer,
)
from apps.chatbot.services.chatbot_services import (
    acquire_stream_lock,
    build_session_payload,
    create_chatbot_session,
    delete_question_from_cache,
    generate_stream,
    get_chatbot_session,
    get_question_from_cache,
    get_valid_chatbot_session,
    is_streaming,
    release_stream_lock,
    save_question_to_cache,
)


class EventStreamRenderer(BaseRenderer):
    media_type = "text/event-stream"
    format = "event-stream"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class ChatbotMessageAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    @extend_schema(
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


class ChatbotStreamAPIView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [EventStreamRenderer, JSONRenderer]

    @extend_schema(
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
                name="Accept",
                type=str,
                location=OpenApiParameter.HEADER,
                required=False,
                description="text/event-stream",
            ),
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
                    'event: start\ndata: {"session_id":56}\n\n'
                    'event: chunk\ndata: {"content":"아이디는"}\n\n'
                    'event: chunk\ndata: {"content":" 본인 인증을 통해"}\n\n'
                    'event: chunk\ndata: {"content":" 찾을 수 있습니다."}\n\n'
                    'event: complete\ndata: {"session_id":56}'
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
                        value={
                            "error_detail": "스트리밍 대상 세션을 찾을 수 없습니다."
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
                        value={"error_detail": "스트리밍 중 오류가 발생했습니다."},
                    )
                ],
            ),
        },
        tags=["chatbot"],
        auth=[],
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
